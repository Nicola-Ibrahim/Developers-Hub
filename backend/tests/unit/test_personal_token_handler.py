import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from identity.application.api_tokens.manage_personal_tokens import PersonalTokenHandler
from identity.application.api_tokens.personal_token_messages import (
    CreatePersonalTokenCommand,
    ListPersonalTokensQuery,
    RotatePersonalTokenCommand,
)
from identity.domain.browser_errors import BrowserAuthenticationRejected
from identity.domain.errors import IdentityValidationError
from identity.domain.records import ApiTokenStatus, PersonalApiToken, SessionPrincipal


def test_personal_tokens_are_bound_to_authenticated_user_project_and_allowed_scopes():
    owner, project_a, project_b = uuid4(), uuid4(), uuid4()
    principal = SessionPrincipal(
        owner, "owner", uuid4(), project_a, "project-a", "developer", (), (), "csrf"
    )

    class Sessions:
        async def authenticate_session(self, **kwargs):
            return (
                (principal, "digest")
                if kwargs["project_id"] in (None, project_a, project_b)
                else None
            )

        async def authorize_browser_operation(self, *_args, **_kwargs):
            return principal

        async def validate_csrf(self, *_args):
            return True

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

    def clock():
        return datetime.now(UTC)

    tokens = Tokens()
    handler = PersonalTokenHandler(
        tokens,
        Sessions(),
        Hasher(),
        Generator(),
        clock,
        ("catalog:read", "resources:read"),
        ("https://hub.test",),
    )
    created, secret = asyncio.run(
        handler.execute(
            CreatePersonalTokenCommand(
                "session", "csrf", "https://hub.test", "build", ("catalog:read",), 2
            )
        )
    )
    assert secret == "one-time-secret"
    assert created.scopes == ("catalog:read",)
    assert asyncio.run(handler.execute(ListPersonalTokensQuery("session", project_a))) == (created,)
    assert asyncio.run(handler.execute(ListPersonalTokensQuery("session", project_b))) == ()
    assert asyncio.run(handler.execute(ListPersonalTokensQuery("session"))) == (created,)

    with pytest.raises(IdentityValidationError):
        asyncio.run(
            handler.execute(
                CreatePersonalTokenCommand(
                    "session", "csrf", "https://hub.test", "wide", ("admin:*",), 2
                )
            )
        )


def test_revoked_browser_session_cannot_rotate_or_create_personal_tokens():
    principal = SessionPrincipal(
        uuid4(), "owner", uuid4(), uuid4(), "project", "developer", (), (), "csrf"
    )

    class Sessions:
        async def authorize_browser_operation(self, *_args, **_kwargs):
            return None

        async def validate_csrf(self, *_args):
            return False

    class Tokens:
        async def lock_personal_token(self, token_id):
            return ApiTokenStatus(token_id, principal.user_id, principal.project_id, None)

    class Unused:
        def digest(self, value):
            return value

        def generate(self):
            return "secret"

    handler = PersonalTokenHandler(
        Tokens(),
        Sessions(),
        Unused(),
        Unused(),
        lambda: datetime.now(UTC),
        ("catalog:read",),
        ("https://hub.test",),
    )
    command = RotatePersonalTokenCommand("revoked", "csrf", "https://hub.test", uuid4())
    with pytest.raises(BrowserAuthenticationRejected):
        asyncio.run(handler.execute(command))


def test_invalid_origin_is_rejected_before_locking_token_identifier():
    token_id = uuid4()

    class Sessions:
        async def authorize_browser_operation(self, *_args, **_kwargs):
            raise AssertionError("origin must fail before session and database locks")

    class Tokens:
        locked = False

        async def lock_personal_token(self, _token_id):
            self.locked = True
            return None

    class Unused:
        def digest(self, value):
            return value

        def generate(self):
            return "secret"

    tokens = Tokens()
    handler = PersonalTokenHandler(
        tokens,
        Sessions(),
        Unused(),
        Unused(),
        lambda: datetime.now(UTC),
        ("catalog:read",),
        ("https://hub.test",),
    )
    with pytest.raises(BrowserAuthenticationRejected):
        asyncio.run(handler.execute(RotatePersonalTokenCommand("session", "csrf", None, token_id)))
    assert not tokens.locked


def test_rotation_repository_call_preserves_original_expiry_and_allowed_scope_ceiling():
    owner, project, old_id, new_id = uuid4(), uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)
    previous = PersonalApiToken(
        old_id, "deploy", project, ("catalog:read",), now + timedelta(minutes=5), now
    )

    class Sessions:
        async def authorize_browser_operation(self, *_args, **_kwargs):
            return SessionPrincipal(
                owner, "owner", uuid4(), project, "project", "developer", (), (), "csrf"
            )

        async def validate_csrf(self, *_args):
            return True

    class Tokens:
        async def lock_personal_token(self, _token_id):
            return ApiTokenStatus(old_id, owner, project, None)

        async def rotate_personal_token(self, **kwargs):
            assert kwargs["allowed_scopes"] == ("catalog:read",)
            return PersonalApiToken(
                new_id, previous.name, project, previous.scopes, previous.expires_at, None
            )

        async def record_token_audit(self, _event):
            return None

    class Generator:
        def generate(self):
            return "replacement-secret"

    class Hasher:
        def digest(self, value):
            return "digest"

    handler = PersonalTokenHandler(
        Tokens(),
        Sessions(),
        Hasher(),
        Generator(),
        lambda: now,
        ("catalog:read",),
        ("https://hub.test",),
    )
    rotated, secret = asyncio.run(
        handler.execute(RotatePersonalTokenCommand("session", "csrf", "https://hub.test", old_id))
    )
    assert secret == "replacement-secret"
    assert rotated.token_id == new_id
    assert rotated.expires_at == previous.expires_at
