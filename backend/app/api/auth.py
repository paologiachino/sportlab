"""Sign-in and session endpoints.

- GET /api/auth/google/login, then Google calls /api/auth/google/callback
- GET /api/auth/me: who is signed in (any status, so a pending user sees it)
- POST /api/auth/refresh: new access and refresh cookies from the refresh cookie
- POST /api/auth/logout: ends the session and clears the cookies
"""

import logging
from datetime import timedelta
from enum import StrEnum
from typing import Annotated

import httpx2
from authlib.integrations.starlette_client import OAuthError, StarletteOAuth2App
from fastapi import APIRouter, Depends, Request, status
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
# Where it lands when the sign-in fails, with ?error=<code> (see LoginError)
LOGIN_PAGE_PATH = "/login"

GoogleClient = Annotated[StarletteOAuth2App | None, Depends(get_google_client)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[Session, Depends(get_db)]


class LoginError(StrEnum):
    """Why a sign-in failed, as the frontend's login page receives it.

    The two Google endpoints are browser navigations, not API calls: an error
    answered as JSON would be shown as raw text. They send the browser back to
    the login page instead, with one of these codes. The codes say no more than
    the JSON errors did.
    """

    CANCELLED = "cancelled"  # the person declined at Google's consent screen
    FAILED = "failed"  # refused answer: wrong state, invalid ID token, replay
    UNVERIFIED_EMAIL = "unverified_email"
    UNAVAILABLE = "unavailable"  # Google unreachable or sign-in not configured


def _login_failed(error: LoginError) -> RedirectResponse:
    return RedirectResponse(
        f"{LOGIN_PAGE_PATH}?error={error}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/google/login", status_code=status.HTTP_302_FOUND)
async def google_login(request: Request, google: GoogleClient, settings: SettingsDep) -> Response:
    """Start the sign-in: redirect the browser to Google.

    Authlib keeps `state`, `nonce` and the PKCE verifier in the short-lived,
    signed login-state cookie until Google sends the browser back.
    """
    if google is None:
        logger.warning("Google sign-in requested but not configured")
        return _login_failed(LoginError.UNAVAILABLE)
    try:
        # Reads Google's published configuration first (cached after the first time)
        return await google.authorize_redirect(request, settings.google_redirect_uri)
    except httpx2.HTTPError as exc:
        logger.warning("Google not reachable: %s", type(exc).__name__)
        return _login_failed(LoginError.UNAVAILABLE)


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
    """Finish the sign-in: check Google's answer, then open a sportlab session.

    Every failure sends the browser back to the login page with an error code.
    """
    if google is None:
        return _login_failed(LoginError.UNAVAILABLE)
    if request.query_params.get("error") == "access_denied":
        # Google's answer when the person presses "Cancel" on the consent screen
        return _login_failed(LoginError.CANCELLED)
    try:
        # Checks state, exchanges the code (with the client secret and the PKCE
        # verifier) and validates the ID token, nonce included
        token = await google.authorize_access_token(request)
    except (OAuthError, JoseError) as exc:
        logger.warning("Google sign-in refused: %s", type(exc).__name__)
        return _login_failed(LoginError.FAILED)
    except httpx2.HTTPError as exc:
        logger.warning("Google not reachable: %s", type(exc).__name__)
        return _login_failed(LoginError.UNAVAILABLE)

    claims = token.get("userinfo") or {}
    if not claims.get("sub") or not claims.get("email"):
        return _login_failed(LoginError.FAILED)
    if claims.get("email_verified") is not True:
        # Without a verified address, ADMIN_EMAIL could be claimed by anyone
        return _login_failed(LoginError.UNVERIFIED_EMAIL)

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
