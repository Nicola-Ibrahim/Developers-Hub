import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from identity.application.api_tokens.manage_personal_tokens import (
    CreatePersonalTokenHandler,
    PersonalTokenQueryHandler,
    RevokePersonalTokenHandler,
    RotatePersonalTokenHandler,
)
from identity.application.api_tokens.personal_token_messages import (
    CreatePersonalTokenCommand,
    ListPersonalTokensQuery,
    RevokePersonalTokenCommand,
    RotatePersonalTokenCommand,
)
from identity.domain.errors import IdentityValidationError
from identity.domain.records import ApiTokenStatus, PersonalApiToken


def test_create_and_list_personal_tokens_are_scoped_to_user_project_and_allowed_scopes():
    owner, project_a, project_b = uuid4(), uuid4(), uuid4()
    class Tokens:
        items = []

        async def create_personal_token(self, **fields):
            token_id = uuid4()
            self.items.append(
                PersonalApiToken(
                    token_id,
                    fields["name"],
                    fields["project_id"],
                    fields["scopes"],
                    fields["expires_at"],
                    None,
                )
            )
            return token_id

        async def record_token_audit(self, _event):
            return None

        async def list_personal_tokens(self, user_id, project_id):
            assert user_id == owner
            return tuple(
                item for item in self.items if project_id is None or item.project_id == project_id
            )

    class Hasher:
        def digest(self, token):
            return "digest:" + token

    class Generator:
        def generate(self):
            return "one-time-secret"

    tokens, hasher = Tokens(), Hasher()
    creator = CreatePersonalTokenHandler(
        tokens,
        hasher,
        Generator(),
        ("catalog:read", "resources:read"),
    )
    reader = PersonalTokenQueryHandler(tokens)
    created, secret = asyncio.run(
        creator.execute(
            CreatePersonalTokenCommand(
                owner, project_a, "build", ("catalog:read",), 2
            )
        )
    )
    assert secret == "one-time-secret"
    assert created.scopes == ("catalog:read",)
    assert asyncio.run(reader.execute(ListPersonalTokensQuery(owner, project_a))) == (created,)
    assert asyncio.run(reader.execute(ListPersonalTokensQuery(owner, project_b))) == ()
    assert asyncio.run(reader.execute(ListPersonalTokensQuery(owner))) == (created,)
    with pytest.raises(IdentityValidationError):
        asyncio.run(
            creator.execute(
                CreatePersonalTokenCommand(
                    owner, project_a, "wide", ("admin:*",), 2
                )
            )
        )


def test_rotation_locks_token_before_owner_check():
    owner, project, token_id = uuid4(), uuid4(), uuid4()

    class Tokens:
        locked = False

        async def lock_personal_token(self, _token_id):
            self.locked = True
            return ApiTokenStatus(token_id, owner, project, None)

    class Hasher:
        def digest(self, value):
            return value

    class Generator:
        def generate(self):
            return "secret"

    tokens = Tokens()
    handler = RotatePersonalTokenHandler(tokens, Hasher(), Generator(), ("catalog:read",))
    assert asyncio.run(handler.execute(RotatePersonalTokenCommand(uuid4(), token_id))) is None
    assert tokens.locked


def test_rotation_keeps_expiry_and_scope_ceiling():
    owner, project, old_id, new_id = uuid4(), uuid4(), uuid4(), uuid4()
    current = datetime.now(UTC)
    old = PersonalApiToken(
        old_id, "deploy", project, ("catalog:read",), current + timedelta(minutes=5), current
    )
    class Tokens:
        async def lock_personal_token(self, _token_id):
            return ApiTokenStatus(old_id, owner, project, None)

        async def rotate_personal_token(self, **kwargs):
            assert kwargs["allowed_scopes"] == ("catalog:read",)
            return PersonalApiToken(new_id, old.name, project, old.scopes, old.expires_at, None)

        async def record_token_audit(self, _event):
            return None

    class Hasher:
        def digest(self, _value):
            return "digest"

    class Generator:
        def generate(self):
            return "replacement-secret"

    handler = RotatePersonalTokenHandler(Tokens(), Hasher(), Generator(), ("catalog:read",))
    rotated, secret = asyncio.run(
        handler.execute(RotatePersonalTokenCommand(owner, old_id))
    )
    assert secret == "replacement-secret"
    assert rotated.token_id == new_id
    assert rotated.expires_at == old.expires_at
    assert rotated.scopes == old.scopes


def test_revoke_handler_has_minimal_dependencies_and_revokes_owned_token():
    owner, project, token_id = uuid4(), uuid4(), uuid4()
    class Tokens:
        async def lock_personal_token(self, _token_id):
            return ApiTokenStatus(token_id, owner, project, None)

        async def revoke_personal_token(self, **kwargs):
            assert kwargs["user_id"] == owner
            assert kwargs["token_id"] == token_id
            return True

    handler = RevokePersonalTokenHandler(Tokens())
    assert asyncio.run(
        handler.execute(RevokePersonalTokenCommand(owner, token_id))
    )
