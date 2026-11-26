"""Typed messages and explicit, scope-local handler dispatch."""

from collections.abc import Awaitable, Callable, Iterable
from types import MappingProxyType
from typing import Any, TypeVar, cast

ResultT = TypeVar("ResultT")


class Command[ResultT]:
    """A state-changing request with a statically known result type."""


class Query[ResultT]:
    """A read request with a statically known result type."""


class RegistrationError(ValueError):
    """The trusted application registration is incomplete or inconsistent."""


class UnsupportedMessage(TypeError):
    """A caller submitted a message not registered by its bounded context."""


class HandlerRegistry:
    def __init__(
        self,
        *,
        commands: Iterable[tuple[type[Command[Any]], type[Any]]],
        queries: Iterable[tuple[type[Query[Any]], type[Any]]],
    ) -> None:
        self.commands = MappingProxyType(self._build(commands, Command))
        self.queries = MappingProxyType(self._build(queries, Query))

    def require_messages(self, messages: Iterable[type[Command[Any]] | type[Query[Any]]]) -> None:
        for message in messages:
            registered = self.commands if issubclass(message, Command) else self.queries
            if message not in registered:
                raise RegistrationError(
                    f"No handler for required message {message.__module__}.{message.__qualname__}"
                )

    @staticmethod
    def _build(
        registrations: Iterable[tuple[type[Any], type[Any]]], marker: type[Any]
    ) -> dict[type[Any], type[Any]]:
        result: dict[type[Any], type[Any]] = {}
        for message, handler in registrations:
            if not isinstance(message, type) or not issubclass(message, marker):
                raise RegistrationError("A message is registered under the wrong kind")
            if message in result:
                raise RegistrationError(f"{message.__qualname__} has more than one handler")
            if not isinstance(handler, type) or not callable(getattr(handler, "execute", None)):
                raise RegistrationError("A registered handler must define execute")
            result[message] = handler
        return result


class Mediator:
    """Resolve only the selected handler from the active DI scope."""

    def __init__(
        self,
        registry: HandlerRegistry,
        resolve: Callable[[type[Any]], Awaitable[Any]],
    ) -> None:
        self._registry = registry
        self._resolve = resolve

    async def execute(self, command: Command[ResultT]) -> ResultT:
        if not isinstance(command, Command):
            raise UnsupportedMessage("Unsupported command")
        handler = await self.resolve(command)
        return cast(ResultT, await handler.execute(command))

    async def query(self, query: Query[ResultT]) -> ResultT:
        if not isinstance(query, Query):
            raise UnsupportedMessage("Unsupported query")
        handler = await self.resolve(query)
        return cast(ResultT, await handler.execute(query))

    async def resolve(self, message: Command[Any] | Query[Any]) -> Any:
        registered = (
            self._registry.commands if isinstance(message, Command) else self._registry.queries
        )
        handler_type = registered.get(type(message))
        if handler_type is None:
            kind = "command" if isinstance(message, Command) else "query"
            raise UnsupportedMessage(f"Unsupported {kind}")
        return await self._resolve(handler_type)
