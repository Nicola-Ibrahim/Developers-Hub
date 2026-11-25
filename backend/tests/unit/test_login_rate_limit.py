import pytest

from api.identity.authentication.login_rate_limit import LoginRequestRateLimiter


def allowed(limiter, peer):
    with limiter.admit(peer) as admitted:
        return admitted


def test_limit_is_sliding_per_peer_and_expires_old_attempts():
    current = [0.0]
    limiter = LoginRequestRateLimiter(
        max_requests=2, window_seconds=10, max_peers=2, clock=lambda: current[0]
    )

    assert allowed(limiter, "peer-a")
    current[0] = 1
    assert allowed(limiter, "peer-a")
    assert not allowed(limiter, "peer-a")
    assert allowed(limiter, "peer-b")
    current[0] = 10.1
    assert allowed(limiter, "peer-a")


def test_new_peers_do_not_evict_active_rate_limits():
    current = [0.0]
    limiter = LoginRequestRateLimiter(
        max_requests=1, max_peers=2, window_seconds=10, clock=lambda: current[0]
    )

    assert allowed(limiter, "peer-a")
    current[0] = 1
    assert allowed(limiter, "peer-b")
    assert not allowed(limiter, "peer-c")
    assert not allowed(limiter, "peer-a")
    current[0] = 10
    assert allowed(limiter, "peer-c")
    assert not allowed(limiter, "peer-b")


def test_concurrent_limit_applies_across_peers_and_releases_on_failure():
    limiter = LoginRequestRateLimiter(max_requests=1, max_concurrent=1)

    with pytest.raises(RuntimeError), limiter.admit("peer-a") as admitted:
        assert admitted
        assert not allowed(limiter, "peer-b")
        raise RuntimeError
    assert allowed(limiter, "peer-b")
