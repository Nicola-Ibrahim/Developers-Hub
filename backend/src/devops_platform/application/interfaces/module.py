"""Typed platform module contract; messages live beside their use cases."""

from abc import ABC, abstractmethod
from typing import TypeVar

from shared.dispatch import Command, Query

ResultT = TypeVar("ResultT")


class DeveloperPlatformModule(ABC):
    @abstractmethod
    async def execute(self, command: Command[ResultT]) -> ResultT: ...

    @abstractmethod
    async def query(self, query: Query[ResultT]) -> ResultT: ...
