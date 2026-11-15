"""Session tokens: signed access tokens, and opaque refresh tokens stored as hashes."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt

ALGORITHM = "HS256"
ISSUER = "sportlab"
ACCESS_TOKEN_TYPE = "access"


class InvalidTokenError(Exception):
    """The access token is missing, malformed, expired or not ours."""


def create_access_token(
    user_id: uuid.UUID, secret_key: str, lifetime: timedelta, now: datetime | None = None
) -> str:
    """A short-lived JWT naming the user.

    It carries no status or role on purpose: those are read from the database on
    every request, so a disabled or demoted user loses access immediately.
    """
    issued = now or datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "iss": ISSUER,
        "iat": issued,
        "exp": issued + lifetime,
    }
    return jwt.encode(claims, secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str, secret_key: str) -> uuid.UUID:
    """The user id inside a valid, unexpired access token; InvalidTokenError otherwise."""
    try:
        claims = jwt.decode(
            token,
            secret_key,
            # Only our algorithm: never trust the one named in the token's header
            # (the classic "alg: none" and algorithm-confusion attacks)
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"require": ["sub", "type", "iss", "iat", "exp"]},
        )
        if claims["type"] != ACCESS_TOKEN_TYPE:
            raise InvalidTokenError("not an access token")
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        # One error for every case: callers answer 401 without telling why
        raise InvalidTokenError(type(exc).__name__) from None


def new_refresh_token() -> str:
    """A random, URL-safe refresh token (256 bits)."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """SHA-256 of a refresh token, the only form stored in the database.

    A plain fast hash is right here, unlike for passwords: the token is 256
    random bits, so it cannot be guessed, and the hash must be searchable.
    """
    return hashlib.sha256(token.encode()).hexdigest()
