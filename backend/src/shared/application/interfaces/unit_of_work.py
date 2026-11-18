"""Application-facing contract for atomic asynchronous operations."""

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

T = TypeVar("T")
R = TypeVar("R")


class UnitOfWork(Protocol):
    async def run(self, action: Callable[[], Awaitable[T]], materialize: Callable[[T], R]) -> R: ...
