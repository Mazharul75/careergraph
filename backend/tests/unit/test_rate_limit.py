"""Unit tests for the fixed-window rate limiters.

Both implementations run the same algorithm; both are tested against the same behavioural
contract. The in-memory limiter uses an injected clock so a "wait for the window to pass"
scenario takes microseconds, and the Redis limiter runs against a dict-backed fake so these
tests need no Redis process.
"""

from __future__ import annotations

import pytest

from app.core.rate_limit import InMemoryRateLimiter, RateLimitDecision, RedisRateLimiter


class ManualClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now


class FakeRedis:
    """The three commands the limiter uses, over a dict.

    Mirrors real Redis semantics closely enough to matter: INCR creates at 1, TTL returns -1
    for a key with no expiry — which is exactly the edge case the limiter must repair.
    """

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = seconds
        return True

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -1)


class BrokenRedis:
    async def incr(self, key: str) -> int:
        raise ConnectionError("redis is down")


# ----------------------------------------------------------------------------------
# InMemoryRateLimiter
# ----------------------------------------------------------------------------------


async def test_allows_up_to_the_limit():
    limiter = InMemoryRateLimiter(clock=ManualClock())
    decisions = [await limiter.hit("k", limit=3, window_seconds=60) for _ in range(3)]
    assert all(d.allowed for d in decisions)


async def test_rejects_the_request_after_the_limit():
    limiter = InMemoryRateLimiter(clock=ManualClock())
    for _ in range(3):
        await limiter.hit("k", limit=3, window_seconds=60)
    decision = await limiter.hit("k", limit=3, window_seconds=60)
    assert not decision.allowed
    assert 1 <= decision.retry_after_seconds <= 61


async def test_window_expiry_resets_the_counter():
    clock = ManualClock()
    limiter = InMemoryRateLimiter(clock=clock)
    for _ in range(3):
        await limiter.hit("k", limit=3, window_seconds=60)
    assert not (await limiter.hit("k", limit=3, window_seconds=60)).allowed

    clock.advance(61)
    assert (await limiter.hit("k", limit=3, window_seconds=60)).allowed


async def test_keys_are_independent():
    limiter = InMemoryRateLimiter(clock=ManualClock())
    for _ in range(3):
        await limiter.hit("alice", limit=3, window_seconds=60)
    assert not (await limiter.hit("alice", limit=3, window_seconds=60)).allowed
    assert (await limiter.hit("bob", limit=3, window_seconds=60)).allowed


async def test_retry_after_shrinks_as_the_window_ages():
    clock = ManualClock()
    limiter = InMemoryRateLimiter(clock=clock)
    for _ in range(3):
        await limiter.hit("k", limit=3, window_seconds=60)

    early = await limiter.hit("k", limit=3, window_seconds=60)
    clock.advance(50)
    late = await limiter.hit("k", limit=3, window_seconds=60)
    assert late.retry_after_seconds < early.retry_after_seconds


# ----------------------------------------------------------------------------------
# RedisRateLimiter
# ----------------------------------------------------------------------------------


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def redis_limiter(fake_redis: FakeRedis) -> RedisRateLimiter:
    return RedisRateLimiter("redis://unused", client=fake_redis)


async def test_redis_allows_up_to_the_limit(redis_limiter: RedisRateLimiter) -> None:
    decisions = [await redis_limiter.hit("k", limit=2, window_seconds=60) for _ in range(2)]
    assert all(d.allowed for d in decisions)


async def test_redis_sets_the_expiry_exactly_once(
    redis_limiter: RedisRateLimiter, fake_redis: FakeRedis
) -> None:
    await redis_limiter.hit("k", limit=5, window_seconds=60)
    assert fake_redis.ttls["k"] == 60
    fake_redis.ttls["k"] = 42  # would be overwritten if EXPIRE ran again
    await redis_limiter.hit("k", limit=5, window_seconds=60)
    assert fake_redis.ttls["k"] == 42


async def test_redis_rejects_with_the_remaining_ttl(
    redis_limiter: RedisRateLimiter, fake_redis: FakeRedis
) -> None:
    for _ in range(2):
        await redis_limiter.hit("k", limit=2, window_seconds=60)
    fake_redis.ttls["k"] = 17  # pretend 43 seconds have passed
    decision = await redis_limiter.hit("k", limit=2, window_seconds=60)
    assert decision == RateLimitDecision(allowed=False, retry_after_seconds=17)


async def test_redis_repairs_a_counter_that_lost_its_expiry(
    redis_limiter: RedisRateLimiter, fake_redis: FakeRedis
) -> None:
    """A crash between INCR and EXPIRE leaves an immortal counter; the limiter must heal it.

    Without the repair, the key never resets and the client is locked out forever — a bug
    that would only ever fire in production, after a badly timed restart.
    """
    fake_redis.counts["k"] = 10  # over the limit, and with no TTL recorded
    decision = await redis_limiter.hit("k", limit=2, window_seconds=60)
    assert not decision.allowed
    assert decision.retry_after_seconds == 60
    assert fake_redis.ttls["k"] == 60  # expiry restored


async def test_redis_failure_fails_open():
    """Redis down must mean "not limited", never "nobody can log in".

    The same posture as /health/ready: Redis is a non-critical dependency. Failing closed
    would convert a cache blip into a self-inflicted authentication outage.
    """
    limiter = RedisRateLimiter("redis://unused", client=BrokenRedis())
    decision = await limiter.hit("k", limit=1, window_seconds=60)
    assert decision.allowed
