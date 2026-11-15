"""Google sign-in: GET /api/auth/google/login, then Google calls /api/auth/google/callback."""

import logging
from datetime import timedelta
from typing import Annotated

import httpx2
from authlib.integrations.starlette_client import OAuthError, StarletteOAuth2App
from fastapi import APIRouter, Depends, HTTPException, Request, status
from joserfc.errors import JoseError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse, Response

from app.core.config import Settings, get_settings
from app.core.cookies import set_session_cookies
from app.core.google import get_google_client
from app.core.security import create_access_token
from app.db.session import get_db
from app.models import User
from app.services.sessions import IssuedToken, SessionLifetimes, start_session
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

    access_token = create_access_token(
        user.id,
        settings.secret_key.get_secret_value(),
        timedelta(minutes=settings.access_token_minutes),
    )
    response = RedirectResponse(AFTER_LOGIN_PATH, status_code=status.HTTP_303_SEE_OTHER)
    set_session_cookies(response, settings, access_token, issued.token)
    return response
