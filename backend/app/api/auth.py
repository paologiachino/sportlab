"""Sign-in and session endpoints.

- GET /api/auth/google/login, then Google calls /api/auth/google/callback
- GET /api/auth/me: who is signed in (any status, so a pending user sees it)
- POST /api/auth/refresh: new access and refresh cookies from the refresh cookie
- POST /api/auth/logout: ends the session and clears the cookies
"""

import logging
from datetime import timedelta
from typing import Annotated

import httpx2
from authlib.integrations.starlette_client import OAuthError, StarletteOAuth2App
from fastapi import APIRouter, Depends, HTTPException, Request, status
from joserfc.errors import JoseError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.api.deps import CurrentUser
from app.core.config import Settings, get_settings
from app.core.cookies import clear_session_cookies, cookie_names, set_session_cookies
from app.core.google import get_google_client
from app.core.security import create_access_token
from app.db.session import get_db
from app.models import User
from app.schemas.user import UserOut
from app.services.sessions import (
    InvalidRefreshTokenError,
    IssuedToken,
    RefreshTokenReuseError,
    SessionLifetimes,
    end_session,
    rotate,
    start_session,
)
from app.services.users import GoogleIdentity, sign_in

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Where the browser lands after signing in: the frontend, served on the same site
AFTER_LOGIN_PATH = "/"

GoogleClient = Annotated[StarletteOAuth2App | None, Depends(get_google_client)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[Session, Depends(get_db)]


def _require(google: StarletteOAuth2App | None) -> StarletteOAuth2App:
    if google is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google login is not configured")
    return google


@router.get("/google/login", status_code=status.HTTP_302_FOUND)
async def google_login(request: Request, google: GoogleClient, settings: SettingsDep) -> Response:
    """Start the sign-in: redirect the browser to Google.

    Authlib keeps `state`, `nonce` and the PKCE verifier in the short-lived,
    signed login-state cookie until Google sends the browser back.
    """
    return await _require(google).authorize_redirect(request, settings.google_redirect_uri)


def _open_session(
    db: Session, identity: GoogleIdentity, settings: Settings
) -> tuple[User, IssuedToken]:
    user = sign_in(db, identity, settings.admin_email_normalised)
    return user, start_session(db, user.id, SessionLifetimes.from_settings(settings))


# Not in the API schema: only Google calls it, as the end of the redirect
@router.get("/google/callback", include_in_schema=False)
async def google_callback(
    request: Request, google: GoogleClient, settings: SettingsDep, db: DbDep
) -> Response:
    """Finish the sign-in: check Google's answer, then open a sportlab session."""
    client = _require(google)
    try:
        # Checks state, exchanges the code (with the client secret and the PKCE
        # verifier) and validates the ID token, nonce included
        token = await client.authorize_access_token(request)
    except (OAuthError, JoseError) as exc:
        logger.warning("Google sign-in refused: %s", type(exc).__name__)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Google sign-in failed") from None
    except httpx2.HTTPError as exc:
        logger.warning("Google not reachable: %s", type(exc).__name__)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Google is not reachable") from None

    claims = token.get("userinfo") or {}
    if not claims.get("sub") or not claims.get("email"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Google sign-in failed")
    if claims.get("email_verified") is not True:
        # Without a verified address, ADMIN_EMAIL could be claimed by anyone
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Google email address not verified")

    identity = GoogleIdentity(
        sub=str(claims["sub"]), email=str(claims["email"]), display_name=claims.get("name")
    )
    # Synchronous database work, off the event loop
    user, issued = await run_in_threadpool(_open_session, db, identity, settings)

    response = RedirectResponse(AFTER_LOGIN_PATH, status_code=status.HTTP_303_SEE_OTHER)
    set_session_cookies(response, settings, _access_token(issued, settings), issued.token)
    return response


def _access_token(issued: IssuedToken, settings: Settings) -> str:
    return create_access_token(
        issued.user_id,
        settings.secret_key.get_secret_value(),
        timedelta(minutes=settings.access_token_minutes),
    )


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    """The signed-in user. 401 when not signed in or the access token expired."""
    return UserOut.model_validate(user)


def _signed_out(settings: Settings, detail: str) -> Response:
    """401 that also clears the cookies, so the browser stops sending dead tokens."""
    response = JSONResponse({"detail": detail}, status_code=status.HTTP_401_UNAUTHORIZED)
    clear_session_cookies(response, settings)
    return response


@router.post("/refresh", status_code=status.HTTP_204_NO_CONTENT)
def refresh(request: Request, settings: SettingsDep, db: DbDep) -> Response:
    """Exchange the refresh cookie for new access and refresh cookies.

    The refresh token is rotated: the old one stops working. Presenting it again
    revokes the whole session (someone copied it). The frontend must refresh
    once at a time, shared by every tab.
    """
    token = request.cookies.get(cookie_names(settings).refresh)
    if not token:
        return _signed_out(settings, "Not signed in")
    try:
        issued = rotate(db, token, SessionLifetimes.from_settings(settings))
    except RefreshTokenReuseError:
        logger.warning("Refresh token reused: session revoked")
        return _signed_out(settings, "Session ended")
    except InvalidRefreshTokenError:
        return _signed_out(settings, "Session ended")

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    set_session_cookies(response, settings, _access_token(issued, settings), issued.token)
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, settings: SettingsDep, db: DbDep) -> Response:
    """End the session and clear the cookies. Safe to call when already signed out."""
    token = request.cookies.get(cookie_names(settings).refresh)
    if token:
        end_session(db, token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookies(response, settings)
    return response
