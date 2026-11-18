"""Translate database failures for the internal first-admin bootstrap flow."""

from collections.abc import Awaitable, Callable
from typing import TypeVar

from devops_platform.application.shared.errors import ledger_unavailable
from shared.infra.persistence.unit_of_work import DatabaseUnavailable, SqlAlchemyUnitOfWork

T = TypeVar("T")
R = TypeVar("R")


class FirstAdminUnitOfWork:
    def __init__(self, unit: SqlAlchemyUnitOfWork) -> None:
        self._unit = unit

    async def run(self, action: Callable[[], Awaitable[T]], materialize: Callable[[T], R]) -> R:
        try:
            return await self._unit.run(action, materialize)
        except DatabaseUnavailable as error:
            raise ledger_unavailable() from error
