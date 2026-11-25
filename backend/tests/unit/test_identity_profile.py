import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from identity.application.profile.handlers import (
    ReadProfileHandler,
    SecurityHistoryHandler,
    UpdateProfileHandler,
)
from identity.application.profile.profile_query import ProfileQuery, SecurityHistoryQuery
from identity.application.profile.update_profile import UpdateProfileCommand
from identity.domain.errors import IdentityValidationError
from identity.domain.records import AccountProfile, SessionPrincipal


def test_profile_read_and_write_are_scoped_to_authenticated_user():
    user_id = uuid4()
    principal = SessionPrincipal(
        user_id, "immutable-name", uuid4(), None, None, None, (), (), "csrf"
    )

    class Sessions:
        async def authenticate_session(self, **_kwargs):
            return principal, None

        async def authorize_session_operation(self, *_args, **_kwargs):
            return principal

        async def validate_csrf(self, *_args):
            return True

    class Users:
        owner_ids = []

        async def load_profile(self, owner_id):
            self.owner_ids.append(owner_id)
            return AccountProfile(owner_id, principal.user_name, None)

        async def update_profile(self, *, user_id, display_name, now):
            self.owner_ids.append(user_id)
            return AccountProfile(user_id, principal.user_name, display_name)

    users = Users()
    handler = UpdateProfileHandler(users)
    profile = asyncio.run(
        ReadProfileHandler(users, Sessions(), SimpleNamespace(digest=str)).execute(
            ProfileQuery("session")
        )
    )
    updated = asyncio.run(
        handler.execute(UpdateProfileCommand(user_id, "Alice"))
    )
    cleared = asyncio.run(
        handler.execute(UpdateProfileCommand(user_id, None))
    )

    assert profile.user_id == updated.user_id == user_id
    assert updated.user_name == "immutable-name"
    assert updated.display_name == "Alice"
    assert cleared.display_name is None
    assert cleared.user_name == "immutable-name"
    assert users.owner_ids == [user_id, user_id, user_id]


@pytest.mark.parametrize("display_name", ["", "   ", "x" * 101])
def test_profile_validation_rejects_invalid_display_name_before_persistence(display_name):
    handler = UpdateProfileHandler(object())
    with pytest.raises(IdentityValidationError):
        asyncio.run(handler.execute(UpdateProfileCommand(uuid4(), display_name)))


def test_security_history_query_uses_only_authenticated_subject_and_is_bounded():
    user_id = uuid4()
    principal = SessionPrincipal(user_id, "alice", uuid4(), None, None, None, (), (), "csrf")

    class Sessions:
        async def authenticate_session(self, **_kwargs):
            return principal, None

    class Users:
        requested = None

        async def list_security_history(self, subject_id, *, limit):
            self.requested = (subject_id, limit)
            return ()

    users = Users()
    handler = SecurityHistoryHandler(users, Sessions(), SimpleNamespace(digest=str))
    asyncio.run(handler.execute(SecurityHistoryQuery("session")))
    assert users.requested == (user_id, 100)


def test_profile_write_uses_router_authorized_actor():
    user_id = uuid4()

    class Users:
        async def update_profile(self, *, user_id: object, display_name: str, now: object):
            return AccountProfile(user_id, "alice", display_name)

    result = asyncio.run(UpdateProfileHandler(Users()).execute(UpdateProfileCommand(user_id, "A")))
    assert result.user_id == user_id
