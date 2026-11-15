"""The Google OpenID Connect client (Authlib).

Authlib runs the security-sensitive parts: `state` against login CSRF, PKCE
against code interception, and the ID token checks (Google's signature from its
published keys, issuer, audience, expiry, `nonce`). Tests replace only the
network, through an httpx2 transport, so those checks still run for real.
"""

from functools import lru_cache

import httpx2
from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App

from app.core.config import Settings, get_settings

GOOGLE_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"
GOOGLE_SCOPES = "openid email profile"


def build_google_client(
    settings: Settings, transport: httpx2.AsyncBaseTransport | None = None
) -> StarletteOAuth2App | None:
    """The Google client, or None when GOOGLE_CLIENT_ID/SECRET are not set."""
    if not settings.google_client_id or not settings.google_client_secret:
        return None
    client_kwargs: dict[str, object] = {
        "scope": GOOGLE_SCOPES,
        "code_challenge_method": "S256",  # PKCE
        "timeout": 10,
    }
    if transport is not None:
        client_kwargs["transport"] = transport
    oauth = OAuth()
    return oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret.get_secret_value(),
        server_metadata_url=GOOGLE_METADATA_URL,
        client_kwargs=client_kwargs,
    )


@lru_cache
def _client_from_settings() -> StarletteOAuth2App | None:
    # One client per process: it caches Google's metadata and keys
    return build_google_client(get_settings())


def get_google_client() -> StarletteOAuth2App | None:
    """FastAPI dependency; tests override it with a client talking to a fake Google."""
    return _client_from_settings()
