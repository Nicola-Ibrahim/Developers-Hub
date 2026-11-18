"""Translate identity database failures at the composition boundary."""

from collections.abc import Awaitable, Callable
from typing import TypeVar

from identity.application.shared.errors import IdentityUnavailable
from shared.infra.persistence.unit_of_work import DatabaseUnavailable, SqlAlchemyUnitOfWork

T = TypeVar("T")
R = TypeVar("R")


class IdentitySessionRevocationUnitOfWork:
    def __init__(self, unit: SqlAlchemyUnitOfWork) -> None:
        self._unit = unit

    async def run(self, action: Callable[[], Awaitable[T]], materialize: Callable[[T], R]) -> R:
        try:
            return await self._unit.run(action, materialize)
        except DatabaseUnavailable as error:
            raise IdentityUnavailable() from error
