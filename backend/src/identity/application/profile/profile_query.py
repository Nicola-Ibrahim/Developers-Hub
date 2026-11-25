from dataclasses import dataclass
from uuid import UUID

from identity.domain.records import AccountProfile, SecurityActivity
from shared.dispatch import Query


@dataclass(frozen=True, slots=True)
class ProfileQuery(Query[AccountProfile]):
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class SecurityHistoryQuery(Query[tuple[SecurityActivity, ...]]):
    actor_id: UUID
