"""Password hashing and token primitives.

This module deliberately knows nothing about users, requests, or the database. It turns strings
into other strings, correctly. That keeps the security-critical code small enough to read in one
sitting and testable without any infrastructure.

Two different token mechanisms are used, on purpose:

* **Access token — a signed JWT.** Self-describing and verified by signature alone, so no
  database round-trip is needed on every request. That is what keeps the API stateless. The
  cost is that it cannot be revoked before it expires, which is why it is short-lived.
* **Refresh token — an opaque random string.** Not a JWT. We need server-side state for it
  anyway (revocation, rotation chains, reuse detection), so signing a JWT would add size and
  parsing cost for no benefit. Only a SHA-256 hash is stored, so a database leak yields nothing
  an attacker can present.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.profiles import RFC_9106_LOW_MEMORY

from app.core.config import get_settings

# --------------------------------------------------------------------------------------
# Password hashing
# --------------------------------------------------------------------------------------

# Argon2id via the RFC 9106 "low memory" profile: 64 MiB, 3 iterations, 4 lanes — the second
# of the two configurations RFC 9106 recommends.
#
# Argon2 is *memory-hard*: it deliberately requires a large working set, which is what makes
# GPU and ASIC cracking expensive, since an attacker can parallelise computation far more
# cheaply than memory. The other RFC profile uses 2 GiB, which is stronger but cannot fit
# alongside the application on a 512 MB free-tier instance — and a hash that gets OOM-killed
# protects nobody.
#
# The cost is real and worth knowing: 64 MiB is allocated *per concurrent hash*, so roughly
# half a dozen simultaneous logins will saturate a free Render instance. Rate limiting on the
# auth endpoints (Phase 5) is what keeps that from being a denial-of-service vector, and
# `password_needs_rehash` below is what lets these parameters be raised later without a reset.
_hasher = PasswordHasher.from_parameters(RFC_9106_LOW_MEMORY)


def hash_password(password: str) -> str:
    """Hash a plaintext password. The salt is generated internally and stored in the output."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Check a password against a stored hash, returning False rather than raising."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """True when a stored hash used weaker parameters than the current profile.

    Lets cost parameters be raised over time: the next successful login transparently upgrades
    the stored hash, with no password reset and no mass migration.
    """
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


# A hash of a throwaway value, computed once at import.
#
# Login must take the same amount of time whether or not the account exists. If the handler
# returns early on "no such user", an attacker can measure response times and enumerate which
# addresses are registered — a real privacy leak, and a shortlist for credential stuffing.
# Verifying against this hash burns the same ~50ms as a genuine check.
DUMMY_PASSWORD_HASH = _hasher.hash(secrets.token_urlsafe(32))


# --------------------------------------------------------------------------------------
# Access tokens (JWT)
# --------------------------------------------------------------------------------------

ACCESS_TOKEN_TYPE = "access"  # noqa: S105 - a claim value, not a credential


@dataclass(frozen=True, slots=True)
class AccessTokenPayload:
    """The validated contents of an access token."""

    user_id: uuid.UUID
    role: str
    jti: uuid.UUID
    expires_at: datetime


class TokenError(Exception):
    """An access token was missing, malformed, expired, or not trustworthy."""


def create_access_token(*, user_id: uuid.UUID, role: str) -> str:
    """Mint a signed access token."""
    settings = get_settings()
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)

    claims = {
        "sub": str(user_id),
        "role": role,
        # `typ` prevents cross-use: a token minted for one purpose cannot be replayed as
        # another simply because both are signed with the same key.
        "typ": ACCESS_TOKEN_TYPE,
        # A unique ID per token, so individual tokens can be denylisted later if needed.
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(
        claims,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> AccessTokenPayload:
    """Verify and decode an access token, or raise ``TokenError``.

    Raises rather than returning None so a caller cannot accidentally treat a failed decode as
    an anonymous-but-valid request.
    """
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            # Pinning the algorithm is essential. Accepting whatever the token's own header
            # declares is the classic JWT vulnerability: an attacker sets alg to "none", or
            # swaps HS256 for RS256 so the public key gets used as an HMAC secret.
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub", "typ", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Token is invalid.") from exc

    if claims.get("typ") != ACCESS_TOKEN_TYPE:
        raise TokenError("Token is not an access token.")

    try:
        return AccessTokenPayload(
            user_id=uuid.UUID(claims["sub"]),
            role=str(claims["role"]),
            jti=uuid.UUID(claims["jti"]),
            expires_at=datetime.fromtimestamp(claims["exp"], tz=UTC),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise TokenError("Token claims are malformed.") from exc


# --------------------------------------------------------------------------------------
# Opaque tokens (refresh tokens, email-verification links, and anything else that is a
# random secret rather than something signed)
# --------------------------------------------------------------------------------------


def generate_opaque_token() -> tuple[str, str]:
    """Create a random single-use token, returning ``(raw_token, token_hash)``.

    The raw value is returned to the caller exactly once and never stored. Only the hash is
    persisted, so a stolen database dump contains nothing that can be presented as a token —
    true of refresh tokens and equally true of an emailed verification link.
    """
    raw = secrets.token_urlsafe(32)  # 256 bits of entropy
    return raw, hash_opaque_token(raw)


def hash_opaque_token(raw_token: str) -> str:
    """Hash an opaque token for storage and lookup.

    Plain SHA-256, not Argon2, and that is correct here: slow hashing exists to make guessing
    *low-entropy human passwords* expensive. This token is 256 random bits — it cannot be
    guessed at any speed — and lookups must be fast enough to sit on the hot path.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# Names kept for every existing call site. Refresh tokens were the first opaque token in the
# system, so the generic implementation above lives under the name every import already uses.
generate_refresh_token = generate_opaque_token
hash_refresh_token = hash_opaque_token


def refresh_token_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=get_settings().refresh_token_expire_days)
