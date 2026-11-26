"""Application-facing contract for atomic asynchronous operations."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


class UnitOfWork(ABC):
    @abstractmethod
    async def run(self, action: Callable[[], Awaitable[T]], materialize: Callable[[T], R]) -> R: ...
