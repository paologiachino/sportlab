"""Session cookies: names and attributes in one place (docs/backend-step-2.md).

Staging and production use the `__Host-` / `__Secure-` name prefixes, which make
the browser enforce HTTPS-only, host-only cookies. Plain http://localhost cannot
carry them, so development uses the same names without prefixes or `Secure`.
"""

from dataclasses import dataclass
from datetime import timedelta

from starlette.responses import Response

from app.core.config import Settings

REFRESH_COOKIE_PATH = "/api/auth"
OAUTH_STATE_LIFETIME = timedelta(minutes=10)


@dataclass(frozen=True)
class CookieNames:
    access: str
    refresh: str
    oauth_state: str


def cookie_names(settings: Settings) -> CookieNames:
    if settings.is_development:
        return CookieNames("sportlab_access", "sportlab_refresh", "sportlab_oauth")
    return CookieNames(
        "__Host-sportlab_access", "__Secure-sportlab_refresh", "__Host-sportlab_oauth"
    )


def set_session_cookies(
    response: Response, settings: Settings, access_token: str, refresh_token: str
) -> None:
    names = cookie_names(settings)
    secure = not settings.is_development
    response.set_cookie(
        names.access,
        access_token,
        max_age=settings.access_token_minutes * 60,
        path="/",
        secure=secure,
        httponly=True,
        samesite="strict",
    )
    response.set_cookie(
        names.refresh,
        refresh_token,
        max_age=settings.refresh_token_days * 24 * 3600,
        # Sent only to the session endpoints, not with every API request
        path=REFRESH_COOKIE_PATH,
        secure=secure,
        httponly=True,
        samesite="strict",
    )


def clear_session_cookies(response: Response, settings: Settings) -> None:
    names = cookie_names(settings)
    secure = not settings.is_development
    response.delete_cookie(names.access, path="/", secure=secure, httponly=True, samesite="strict")
    response.delete_cookie(
        names.refresh, path=REFRESH_COOKIE_PATH, secure=secure, httponly=True, samesite="strict"
    )
