"""Readiness contract for the API and other runtime entry points."""

from typing import Literal, Protocol

ReadinessStatus = Literal["ready", "schema_not_ready", "database_unavailable"]


class ReadinessProbe(Protocol):
    async def inspect(self) -> ReadinessStatus: ...
