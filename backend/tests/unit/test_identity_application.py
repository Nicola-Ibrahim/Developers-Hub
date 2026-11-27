import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from identity.application.api_tokens.authenticate_api_token.handler import (
    AuthenticateApiTokenHandler,
)
from identity.application.api_tokens.authenticate_api_token.query import AuthenticateApiTokenQuery
from identity.application.api_tokens.revoke_api_token.command import RevokeApiTokenCommand
from identity.application.api_tokens.revoke_api_token.handler import RevokeApiTokenHandler
from identity.domain.aggregates.api_token import ApiTokenAuthenticationDetails
from identity.domain.errors import AuthenticationRejected
from identity.domain.records import ApiTokenStatus
from identity.infra.security.opaque_secrets import PepperedTokenHasher, token_digest

NOW = datetime(2026, 1, 1, tzinfo=UTC)
TOKEN = "a" * 40


class FakeRepository:
    def __init__(self, credential=None, token=None):
        self.credential = credential
        self.token = token
        self.calls = []

    async def find_token_credential(self, digest):
        self.calls.append(("find_token_credential", digest))
        return self.credential

    async def record_token_audit(self, event):
        self.calls.append(("record_token_audit", event))

    async def find_api_token(self, token_id):
        self.calls.append(("find_api_token", token_id))
        return self.token

    async def revoke_api_token(self, token_id, revoked_at):
        self.calls.append(("revoke_api_token", token_id, revoked_at))


class FakeTransaction:
    def __init__(self, repository):
        self.repository = repository

    async def run(self, action):
        return await action(self.repository)


class FakeHasher:
    def digest(self, token):
        return "synthetic-digest"


def test_authenticate_api_token_reads_repository_and_rejects_malformed_before_query():
    now = datetime.now(UTC)
    snapshot = ApiTokenAuthenticationDetails(
        uuid4(),
        uuid4(),
        uuid4(),
        "developer",
        ("catalog:read",),
        True,
        now + timedelta(hours=1),
        None,
    )
    repository = FakeRepository(credential=snapshot)
    result = asyncio.run(
        AuthenticateApiTokenHandler(
            FakeTransaction(repository), PepperedTokenHasher("p" * 32)
        ).execute(AuthenticateApiTokenQuery(token=TOKEN))
    )
    assert result.role == "developer"
    assert result.scopes == frozenset({"catalog:read"})
    assert repository.calls == [("find_token_credential", token_digest(TOKEN, "p" * 32))]

    for invalid in (None, "short", "x" * 257):
        with pytest.raises(AuthenticationRejected):
            asyncio.run(
                AuthenticateApiTokenHandler(
                    FakeTransaction(repository), PepperedTokenHasher("p" * 32)
                ).execute(AuthenticateApiTokenQuery(token=invalid))
            )
    assert len(repository.calls) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"user_active": False},
        {"revoked_at": NOW},
        {"expires_at": NOW},
        {"role": None},
    ],
)
def test_authenticate_api_token_rejects_invalid_repository_snapshot(changes):
    now = datetime.now(UTC)
    values = dict(
        token_id=uuid4(),
        user_id=uuid4(),
        project_id=uuid4(),
        role="developer",
        scopes=("catalog:read",),
        user_active=True,
        expires_at=now + timedelta(hours=1),
        revoked_at=None,
    )
    values.update(changes)
    repository = FakeRepository(credential=ApiTokenAuthenticationDetails(**values))
    with pytest.raises(AuthenticationRejected):
        asyncio.run(
            AuthenticateApiTokenHandler(FakeTransaction(repository), FakeHasher()).execute(
                AuthenticateApiTokenQuery(token=TOKEN)
            )
        )


def test_revoke_api_token_is_idempotent_and_audits_only_first_revoke():
    token_id = uuid4()
    missing = FakeRepository(token=None)
    assert (
        asyncio.run(
            RevokeApiTokenHandler(FakeTransaction(missing)).execute(
                RevokeApiTokenCommand(token_id=token_id)
            )
        )
        is False
    )
    assert [call[0] for call in missing.calls] == ["find_api_token"]

    existing = ApiTokenStatus(token_id, uuid4(), uuid4(), None)
    repository = FakeRepository(token=existing)
    assert (
        asyncio.run(
            RevokeApiTokenHandler(FakeTransaction(repository)).execute(
                RevokeApiTokenCommand(token_id=token_id)
            )
        )
        is True
    )
    assert [call[0] for call in repository.calls] == [
        "find_api_token",
        "revoke_api_token",
        "record_token_audit",
    ]
    assert repository.calls[-1][1].action == "token_revoked"

    repository.calls.clear()
    repository.token = ApiTokenStatus(token_id, existing.user_id, existing.project_id, NOW)
    assert (
        asyncio.run(
            RevokeApiTokenHandler(FakeTransaction(repository)).execute(
                RevokeApiTokenCommand(token_id=token_id)
            )
        )
        is True
    )
    assert [call[0] for call in repository.calls] == ["find_api_token"]
