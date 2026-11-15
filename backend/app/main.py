"""sportlab FastAPI application."""

import logging

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api import auth, health
from app.core.config import get_settings
from app.core.cookies import OAUTH_STATE_LIFETIME, cookie_names
from app.core.csrf import RequireCSRFHeader

logger = logging.getLogger(__name__)

# Validated at import, so the server refuses to start with a broken environment
# instead of failing later on the first request that needs a missing value.
settings = get_settings()

if not settings.is_development and not settings.admin_email_normalised:
    logger.warning("ADMIN_EMAIL is not set: no account will become administrator")

app = FastAPI(title="sportlab")

# Signed cookie holding the Google sign-in state (state, nonce, PKCE verifier)
# between the redirect to Google and the callback; nothing else uses it.
# SameSite=Lax because the callback is a navigation coming from Google's site.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key.get_secret_value(),
    session_cookie=cookie_names(settings).oauth_state,
    max_age=int(OAUTH_STATE_LIFETIME.total_seconds()),
    path="/",
    same_site="lax",
    https_only=not settings.is_development,
)

# State-changing API requests need X-Requested-With (see app/core/csrf.py)
app.add_middleware(RequireCSRFHeader)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
