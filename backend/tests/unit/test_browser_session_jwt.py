from datetime import UTC, datetime, timedelta

import pytest

from identity.infra.security.jwt import JwtSessionTokens


def test_browser_session_jwt_requires_intact_signature() -> None:
    tokens = JwtSessionTokens("test-signing-material-" * 3)
    now = datetime.now(UTC)
    token = tokens.issue("account", now, now + timedelta(minutes=1))
    assert tokens.verify(token)

    header, payload, signature = token.split(".")
    changed = ("A" if signature[0] != "A" else "B") + signature[1:]
    assert not tokens.verify(f"{header}.{payload}.{changed}")
    assert not tokens.verify("old-opaque-cookie")


def test_browser_session_jwt_rejects_expired_token() -> None:
    tokens = JwtSessionTokens("test-signing-material-" * 3)
    now = datetime.now(UTC)
    token = tokens.issue("account", now - timedelta(minutes=2), now - timedelta(minutes=1))
    assert not tokens.verify(token)


@pytest.mark.parametrize(
    "token",
    ["", "not-a-jwt", "a.b.c", "..", "eyJhbGciOiJub25lIn0.eyJzdWIiOiJhY2NvdW50In0."],
)
def test_browser_session_jwt_rejects_hostile_malformed_tokens(token: str) -> None:
    tokens = JwtSessionTokens("test-signing-material-" * 3)
    assert not tokens.verify(token)
