"""A fake Google for the sign-in tests: no test ever calls the real one.

It answers the three requests Authlib makes (discovery document, public keys,
token exchange) through an httpx2 MockTransport, and signs ID tokens with an
RSA key generated for the test run. Authlib's own checks (state, nonce, PKCE,
signature, issuer, audience, expiry) therefore run unchanged.
"""

import base64
import json
import secrets
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs

import httpx2
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from app.core.google import GOOGLE_METADATA_URL

ISSUER = "https://accounts.google.com"
AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"


def new_rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@dataclass(frozen=True)
class Account:
    """A synthetic Google account."""

    sub: str = field(default_factory=lambda: f"synthetic-{secrets.token_hex(8)}")
    email: str = field(default_factory=lambda: f"user-{secrets.token_hex(4)}@example.com")
    name: str = "Synthetic User"
    email_verified: bool = True


class FakeGoogle:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.key = new_rsa_key()
        self.kid = "fake-key-1"
        self._codes: dict[str, dict[str, object]] = {}
        self.token_requests: list[dict[str, list[str]]] = []
        # URLs (without query) that fail as if Google were unreachable
        self.unreachable: set[str] = set()

    @property
    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self._handle)

    def issue_code(
        self,
        account: Account,
        nonce: str,
        signing_key: rsa.RSAPrivateKey | None = None,
        **claim_overrides: object,
    ) -> str:
        """What Google does when the person approves: a one-time code for these claims."""
        now = int(time.time())
        claims: dict[str, object] = {
            "iss": ISSUER,
            "aud": self.client_id,
            "sub": account.sub,
            "email": account.email,
            "email_verified": account.email_verified,
            "name": account.name,
            "nonce": nonce,
            "iat": now,
            "exp": now + 3600,
        }
        claims.update(claim_overrides)
        code = secrets.token_urlsafe(16)
        self._codes[code] = {"claims": claims, "key": signing_key or self.key}
        return code

    def _id_token(self, claims: dict[str, object], key: rsa.RSAPrivateKey) -> str:
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": self.kid})

    def _jwks(self) -> dict[str, object]:
        jwk = json.loads(RSAAlgorithm.to_jwk(self.key.public_key()))
        jwk.update(kid=self.kid, use="sig", alg="RS256")
        return {"keys": [jwk]}

    def _client_authenticated(self, request: httpx2.Request, form: dict[str, list[str]]) -> bool:
        expected = f"{self.client_id}:{self.client_secret}"
        header = request.headers.get("authorization", "")
        if header.startswith("Basic "):
            return base64.b64decode(header[6:]).decode() == expected
        return form.get("client_secret") == [self.client_secret]

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        url = str(request.url).split("?")[0]
        if url in self.unreachable:
            raise httpx2.ConnectError("Google unreachable", request=request)
        if request.method == "GET" and url == GOOGLE_METADATA_URL:
            return httpx2.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": AUTHORIZE_URL,
                    "token_endpoint": TOKEN_URL,
                    "jwks_uri": JWKS_URL,
                    "id_token_signing_alg_values_supported": ["RS256"],
                },
            )
        if request.method == "GET" and url == JWKS_URL:
            return httpx2.Response(200, json=self._jwks())
        if request.method == "POST" and url == TOKEN_URL:
            form = parse_qs(request.content.decode())
            self.token_requests.append(form)
            grant = self._codes.pop(form.get("code", [""])[0], None)  # one use only
            if (
                grant is None
                or not form.get("code_verifier")
                or not self._client_authenticated(request, form)
            ):
                return httpx2.Response(400, json={"error": "invalid_grant"})
            return httpx2.Response(
                200,
                json={
                    "access_token": "fake-google-access-token",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "scope": "openid email profile",
                    "id_token": self._id_token(grant["claims"], grant["key"]),  # type: ignore[arg-type]
                },
            )
        return httpx2.Response(404)
