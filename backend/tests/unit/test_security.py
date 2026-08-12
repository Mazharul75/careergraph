"""Password hashing and token primitives."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import (
    ACCESS_TOKEN_TYPE,
    DUMMY_PASSWORD_HASH,
    TokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

VALID_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def _jwt_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give this module a deterministic signing key.

    The unit conftest strips settings from the environment, so a key must be supplied here.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/careergraph_test")
    monkeypatch.setenv("JWT_SECRET_KEY", "unit-test-signing-key-not-used-anywhere-else")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestPasswordHashing:
    def test_hash_is_not_the_password(self) -> None:
        digest = hash_password(VALID_PASSWORD)
        assert VALID_PASSWORD not in digest
        assert digest.startswith("$argon2id$")

    def test_correct_password_verifies(self) -> None:
        assert verify_password(hash_password(VALID_PASSWORD), VALID_PASSWORD) is True

    def test_wrong_password_does_not_verify(self) -> None:
        assert verify_password(hash_password(VALID_PASSWORD), "not-the-password") is False

    def test_same_password_hashes_differently_each_time(self) -> None:
        # A random salt per hash. Without it, identical passwords produce identical hashes, and
        # one leaked database instantly reveals every account sharing a common password.
        assert hash_password(VALID_PASSWORD) != hash_password(VALID_PASSWORD)

    def test_malformed_hash_is_rejected_not_raised(self) -> None:
        # Garbage in the column must fail closed, never crash the login handler.
        assert verify_password("not-a-real-hash", VALID_PASSWORD) is False

    def test_dummy_hash_never_matches_a_real_password(self) -> None:
        # Used for constant-time login against non-existent accounts; it must not accidentally
        # authenticate anyone.
        assert verify_password(DUMMY_PASSWORD_HASH, VALID_PASSWORD) is False

    def test_verification_cost_is_comparable_for_real_and_dummy_hashes(self) -> None:
        """The timing-attack defence has to actually hold.

        A wrong password against a real hash and a check against the dummy hash must cost
        roughly the same, or login response time leaks whether an account exists. The bound is
        loose because CI runners are noisy; it still catches the regression that matters —
        someone replacing the dummy check with an early return.
        """
        real_hash = hash_password(VALID_PASSWORD)

        start = time.perf_counter()
        verify_password(real_hash, "wrong-password-entirely")
        real_elapsed = time.perf_counter() - start

        start = time.perf_counter()
        verify_password(DUMMY_PASSWORD_HASH, "wrong-password-entirely")
        dummy_elapsed = time.perf_counter() - start

        assert 0.25 < (dummy_elapsed / real_elapsed) < 4.0


class TestAccessTokens:
    def test_round_trip_preserves_identity_and_role(self) -> None:
        user_id = uuid.uuid4()
        payload = decode_access_token(create_access_token(user_id=user_id, role="recruiter"))

        assert payload.user_id == user_id
        assert payload.role == "recruiter"

    def test_each_token_has_a_unique_jti(self) -> None:
        user_id = uuid.uuid4()
        first = decode_access_token(create_access_token(user_id=user_id, role="job_seeker"))
        second = decode_access_token(create_access_token(user_id=user_id, role="job_seeker"))

        assert first.jti != second.jti

    def test_tampered_payload_is_rejected(self) -> None:
        # Flip a character in the payload segment; the signature no longer matches.
        token = create_access_token(user_id=uuid.uuid4(), role="job_seeker")
        header, payload, signature = token.split(".")
        tampered = f"{header}.{payload[:-2]}XY.{signature}"

        with pytest.raises(TokenError):
            decode_access_token(tampered)

    def test_token_signed_with_another_key_is_rejected(self) -> None:
        forged = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "role": "recruiter",
                "typ": ACCESS_TOKEN_TYPE,
                "jti": str(uuid.uuid4()),
                "iat": int(datetime.now(UTC).timestamp()),
                "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            },
            "an-attackers-own-key-padded-to-a-realistic-length-000000",
            algorithm="HS256",
        )
        with pytest.raises(TokenError):
            decode_access_token(forged)

    def test_expired_token_is_rejected(self) -> None:
        settings = get_settings()
        past = datetime.now(UTC) - timedelta(hours=2)
        expired = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "role": "job_seeker",
                "typ": ACCESS_TOKEN_TYPE,
                "jti": str(uuid.uuid4()),
                "iat": int(past.timestamp()),
                "exp": int((past + timedelta(minutes=15)).timestamp()),
            },
            settings.jwt_secret_key.get_secret_value(),
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(TokenError):
            decode_access_token(expired)

    def test_alg_none_token_is_rejected(self) -> None:
        """The classic JWT attack: strip the signature and declare alg=none.

        Only defeated because decode_access_token pins `algorithms=[...]` instead of trusting
        the algorithm the token declares about itself.
        """
        unsigned = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "role": "recruiter",
                "typ": ACCESS_TOKEN_TYPE,
                "jti": str(uuid.uuid4()),
                "iat": int(datetime.now(UTC).timestamp()),
                "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            },
            key="",
            algorithm="none",
        )
        with pytest.raises(TokenError):
            decode_access_token(unsigned)

    def test_token_of_the_wrong_type_is_rejected(self) -> None:
        settings = get_settings()
        wrong_type = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "role": "job_seeker",
                "typ": "refresh",
                "jti": str(uuid.uuid4()),
                "iat": int(datetime.now(UTC).timestamp()),
                "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            },
            settings.jwt_secret_key.get_secret_value(),
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(TokenError):
            decode_access_token(wrong_type)

    @pytest.mark.parametrize("garbage", ["", "not.a.token", "a.b", "...."])
    def test_garbage_input_raises_token_error(self, garbage: str) -> None:
        with pytest.raises(TokenError):
            decode_access_token(garbage)


class TestRefreshTokens:
    def test_raw_token_is_not_the_stored_hash(self) -> None:
        raw, digest = generate_refresh_token()
        assert raw != digest
        assert len(digest) == 64  # sha256 hex

    def test_hash_is_deterministic(self) -> None:
        raw, digest = generate_refresh_token()
        assert hash_refresh_token(raw) == digest

    def test_tokens_are_unique(self) -> None:
        tokens = {generate_refresh_token()[0] for _ in range(100)}
        assert len(tokens) == 100

    def test_token_carries_enough_entropy(self) -> None:
        # token_urlsafe(32) → 32 random bytes, base64url-encoded to ~43 characters.
        raw, _ = generate_refresh_token()
        assert len(raw) >= 43
