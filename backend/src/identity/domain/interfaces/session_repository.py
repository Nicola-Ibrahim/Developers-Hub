"""Session persistence operations."""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from identity.domain.aggregates.session import Session
from identity.domain.records import SessionPrincipal


class SessionRepository(ABC):
    @abstractmethod
    async def load_for_revocation(self, user_id: UUID, session_id: UUID) -> Session | None: ...

    @abstractmethod
    async def save_revocation(self, session: Session) -> None: ...

    @abstractmethod
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

    @abstractmethod
    async def authenticate_session(
        self, *, token_digest: str, project_id: UUID | None, now: datetime
    ) -> tuple[SessionPrincipal, str] | None: ...

    @abstractmethod
    async def authorize_session_operation(
        self,
        token_digest: str,
        project_id: UUID | None,
        now: datetime,
        *,
        lock_for_mutation: bool = False,
    ) -> SessionPrincipal | None: ...

    @abstractmethod
    async def rotate_csrf(self, token_digest: str, csrf_digest: str, now: datetime) -> bool: ...

    @abstractmethod
    async def select_project(
        self, *, token_digest: str, project_id: UUID, now: datetime
    ) -> SessionPrincipal | None: ...

    @abstractmethod
    async def logout(self, token_digest: str, now: datetime) -> None: ...

    @abstractmethod
    async def logout_all(self, user_id: UUID, now: datetime) -> int: ...

    @abstractmethod
    async def revoke_user_sessions(self, user_id: UUID, now: datetime) -> None: ...

    @abstractmethod
    async def list_sessions(
        self, user_id: UUID, current_session_id: UUID, now: datetime
    ) -> tuple[Session, ...]: ...

    @abstractmethod
    async def validate_csrf(self, token_digest: str, csrf_digest: str) -> bool: ...
