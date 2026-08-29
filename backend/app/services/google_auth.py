"""Verifying a Google Sign-In ID token.

**What "Sign in with Google" actually hands us.** The frontend's Google button (Google
Identity Services) runs entirely client-side and returns a **signed JWT** — an ID token —
asserting "Google vouches that this person controls this email address." Our job is only to
check that signature and read the claims; there is no client secret and no server-to-server
call in this flow, which is why no ``GOOGLE_CLIENT_SECRET`` appears anywhere in this codebase.

**Why PyJWT instead of the ``google-auth`` package.** ``google-auth``'s token verifier pulls in
its own HTTP transport (``requests``), a second HTTP library alongside ``httpx``, for one
function call. PyJWT is already a dependency for our own access tokens, and its
``PyJWKClient`` does exactly the same job — fetch Google's public signing keys, cache them,
verify the signature — with no new dependency at all.

The three checks that actually matter are the signature, the ``aud`` claim (must be *our*
client id, or any ID token from any Google app becomes valid here), and expiry. PyJWT enforces
all three when given ``audience=`` and default options.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import jwt

from app.services.exceptions import GoogleTokenInvalidError

_GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")

# Module-level: PyJWKClient caches fetched keys internally, and constructing it fresh per
# request would throw that cache away and refetch Google's certs on every sign-in.
_jwks_client: jwt.PyJWKClient | None = None


def _get_jwks_client() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(_GOOGLE_JWKS_URL)
    return _jwks_client


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    """What we trust from a verified Google ID token — nothing else is read from it."""

    subject: str  # the `sub` claim: Google's stable, permanent id for this account
    email: str
    email_verified: bool
    full_name: str | None


class GoogleTokenVerifier(Protocol):
    """Abstracted the same way the task queue is, so a unit test can supply a fake identity
    without ever constructing a real signed JWT or reaching Google's network."""

    def __call__(self, id_token: str, *, client_id: str) -> GoogleIdentity: ...


def verify_google_id_token(id_token: str, *, client_id: str) -> GoogleIdentity:
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=list(_GOOGLE_ISSUERS),
        )
    except jwt.PyJWTError as exc:
        raise GoogleTokenInvalidError from exc

    email = claims.get("email")
    subject = claims.get("sub")
    if not email or not subject:
        raise GoogleTokenInvalidError

    return GoogleIdentity(
        subject=str(subject),
        email=str(email).strip().lower(),
        email_verified=bool(claims.get("email_verified", False)),
        full_name=claims.get("name"),
    )
