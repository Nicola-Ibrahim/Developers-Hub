"""Persistence contract for loading and saving an owned session revocation."""

from typing import Protocol
from uuid import UUID

from identity.domain.aggregates.session import Session


class SessionRevocationRepository(Protocol):
    async def load_for_revocation(self, user_id: UUID, session_id: UUID) -> Session | None: ...

    async def save_revocation(self, session: Session) -> None: ...
