"""Readiness contract for the API and other runtime entry points."""

from abc import ABC, abstractmethod
from typing import Literal

ReadinessStatus = Literal["ready", "schema_not_ready", "database_unavailable"]


class ReadinessProbe(ABC):
    @abstractmethod
    async def inspect(self) -> ReadinessStatus: ...
