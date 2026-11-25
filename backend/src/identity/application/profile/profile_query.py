from dataclasses import dataclass, field

from identity.domain.records import AccountProfile, SecurityActivity
from shared.dispatch import Query


@dataclass(frozen=True, slots=True)
class ProfileQuery(Query[AccountProfile]):
    session_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class SecurityHistoryQuery(Query[tuple[SecurityActivity, ...]]):
    session_token: str = field(repr=False)
