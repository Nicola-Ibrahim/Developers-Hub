"""Session persistence operations."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from identity.domain.aggregates.session import Session
from identity.domain.records import SessionPrincipal


class SessionRepository(Protocol):
    async def load_for_revocation(self, user_id: UUID, session_id: UUID) -> Session | None: ...

    async def save_revocation(self, session: Session) -> None: ...

    async def create_login_session(
        self,
        *,
        user_id: UUID,
        user_name: str,
        credential_version: int,
        token_digest: str,
        csrf_digest: str,
        now: datetime,
    ) -> tuple[SessionPrincipal, UUID, datetime]: ...

    async def authenticate_session(
        self, *, token_digest: str, project_id: UUID | None, now: datetime
    ) -> tuple[SessionPrincipal, str] | None: ...

    async def authorize_session_operation(
        self,
        token_digest: str,
        project_id: UUID | None,
        now: datetime,
        *,
        lock_for_mutation: bool = False,
    ) -> SessionPrincipal | None: ...

    async def rotate_csrf(self, token_digest: str, csrf_digest: str, now: datetime) -> bool: ...

    async def select_project(
        self, *, token_digest: str, project_id: UUID, now: datetime
    ) -> SessionPrincipal | None: ...

    async def logout(self, token_digest: str, now: datetime) -> None: ...

    async def logout_all(self, user_id: UUID, now: datetime) -> int: ...

    async def revoke_user_sessions(self, user_id: UUID, now: datetime) -> None: ...

    async def list_sessions(
        self, user_id: UUID, current_session_id: UUID, now: datetime
    ) -> tuple[Session, ...]: ...

    async def validate_csrf(self, token_digest: str, csrf_digest: str) -> bool: ...
