"""Identity account persistence operations used by account use cases."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from identity.domain.records import (
    AccountCredentials,
    AccountProfile,
    AccountSessionDetails,
    SecurityActivity,
)


class UserRepository(Protocol):
    async def load_profile(self, user_id: UUID) -> AccountProfile | None: ...

    async def update_profile(
        self, *, user_id: UUID, display_name: str | None, now: datetime
    ) -> AccountProfile | None: ...

    async def list_security_history(
        self, user_id: UUID, *, limit: int
    ) -> tuple[SecurityActivity, ...]: ...

    async def issue_password_setup(
        self,
        *,
        user_id: UUID,
        digest: str,
        expires_at: datetime,
        actor_id: UUID,
        now: datetime,
    ) -> None: ...

    async def find_login_account(self, user_name: str) -> AccountCredentials | None: ...

    async def record_login_attempt(
        self,
        *,
        user_name: str,
        username_digest: str,
        expected_version: int | None,
        accepted: bool,
        now: datetime,
        replacement_password_hash: str | None = None,
    ) -> tuple[UUID, str, int] | None: ...

    async def load_session_account(
        self, user_id: UUID, *, lock_for_update: bool = False, shared_lock: bool = False
    ) -> AccountSessionDetails | None: ...

    async def change_password(
        self, *, user_id: UUID, expected_version: int, password_hash: str, now: datetime
    ) -> bool: ...

    async def create_user(
        self, user_name: str, password_hash: str, actor_id: UUID | None, now: datetime
    ) -> UUID: ...

    async def set_user_active(
        self, *, actor_id: UUID, user_id: UUID, active: bool, now: datetime
    ) -> bool: ...

    async def consume_password_setup(
        self, *, digest: str, password_hash: str, now: datetime
    ) -> UUID | None: ...
