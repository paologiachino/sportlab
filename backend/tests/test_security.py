import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.security import (
    ALGORITHM,
    ISSUER,
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_refresh_token,
    new_refresh_token,
)

KEY = "k" * 32
OTHER_KEY = "o" * 32
FIFTEEN_MINUTES = timedelta(minutes=15)


def test_access_token_round_trip() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id, KEY, FIFTEEN_MINUTES)

    assert decode_access_token(token, KEY) == user_id


def test_access_token_carries_only_identity() -> None:
    token = create_access_token(uuid.uuid4(), KEY, FIFTEEN_MINUTES)
    claims = jwt.decode(token, KEY, algorithms=[ALGORITHM], issuer=ISSUER)

    assert set(claims) == {"sub", "type", "iss", "iat", "exp"}


def test_expired_access_token_is_refused() -> None:
    issued = datetime.now(UTC) - timedelta(minutes=20)
    token = create_access_token(uuid.uuid4(), KEY, FIFTEEN_MINUTES, now=issued)

    with pytest.raises(InvalidTokenError, match="ExpiredSignatureError"):
        decode_access_token(token, KEY)


def test_token_signed_with_another_key_is_refused() -> None:
    token = create_access_token(uuid.uuid4(), OTHER_KEY, FIFTEEN_MINUTES)

    with pytest.raises(InvalidTokenError, match="InvalidSignatureError"):
        decode_access_token(token, KEY)


def unsigned_token(claims: dict[str, object]) -> str:
    """A token with "alg": "none", as an attacker would forge it."""
    return jwt.encode(claims, key=None, algorithm="none")


def valid_claims(**overrides: object) -> dict[str, object]:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iss": ISSUER,
        "iat": now,
        "exp": now + FIFTEEN_MINUTES,
    }
    claims.update(overrides)
    return claims


def test_unsigned_token_is_refused() -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token(unsigned_token(valid_claims()), KEY)


@pytest.mark.parametrize(
    "claims",
    [
        valid_claims(type="refresh"),
        valid_claims(iss="someone-else"),
        valid_claims(sub="not-a-uuid"),
        {k: v for k, v in valid_claims().items() if k != "sub"},
        {k: v for k, v in valid_claims().items() if k != "exp"},
    ],
    ids=["wrong-type", "wrong-issuer", "bad-subject", "no-subject", "no-expiry"],
)
def test_malformed_claims_are_refused(claims: dict[str, object]) -> None:
    token = jwt.encode(claims, KEY, algorithm=ALGORITHM)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, KEY)


@pytest.mark.parametrize("token", ["", "garbage", "a.b.c"])
def test_garbage_is_refused(token: str) -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, KEY)


def test_refresh_tokens_are_random_and_long() -> None:
    tokens = {new_refresh_token() for _ in range(100)}

    assert len(tokens) == 100
    assert all(len(token) >= 43 for token in tokens)  # 32 bytes in URL-safe base64


def test_refresh_token_hash() -> None:
    token = new_refresh_token()
    digest = hash_refresh_token(token)

    assert digest == hash_refresh_token(token)
    assert digest != token
    assert len(digest) == 64
    assert hash_refresh_token(new_refresh_token()) != digest
