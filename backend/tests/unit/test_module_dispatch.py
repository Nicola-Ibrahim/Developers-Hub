"""Contract checks for explicit, lazy context module registration."""

import asyncio

import pytest
from dishka import Provider, Scope, make_async_container

from shared.dispatch import (
    Command,
    HandlerRegistry,
    Mediator,
    Query,
    RegistrationError,
    UnsupportedMessage,
)
from shared.infra.dispatch import register_handlers


class ChangeName(Command[str]):
    pass


class ReadName(Query[str]):
    pass


class ChangeNameHandler:
    async def execute(self, message: ChangeName) -> str:
        return "changed"


class ReadNameHandler:
    async def execute(self, message: ReadName) -> str:
        return "read"


def test_registry_rejects_duplicates_and_wrong_message_kinds() -> None:
    with pytest.raises(RegistrationError, match="more than one"):
        HandlerRegistry(commands=[(ChangeName, ChangeNameHandler)] * 2, queries=[])
    with pytest.raises(RegistrationError, match="wrong kind"):
        HandlerRegistry(commands=[(ReadName, ReadNameHandler)], queries=[])


def test_dispatch_resolves_only_selected_handler_and_rejects_unknown() -> None:
    selected: list[type[object]] = []
    registry = HandlerRegistry(
        commands=[(ChangeName, ChangeNameHandler)], queries=[(ReadName, ReadNameHandler)]
    )

    async def resolve(handler: type[object]) -> object:
        selected.append(handler)
        return handler()

    module = Mediator(registry, resolve)

    async def run() -> None:
        assert await module.execute(ChangeName()) == "changed"
        assert selected == [ChangeNameHandler]
        assert await module.query(ReadName()) == "read"
        assert selected == [ChangeNameHandler, ReadNameHandler]
        with pytest.raises(UnsupportedMessage, match="Unsupported command"):
            await Mediator(HandlerRegistry(commands=[], queries=[]), resolve).execute(ChangeName())

    asyncio.run(run())


def test_registry_also_supplies_dishka_handler_bindings() -> None:
    registry = HandlerRegistry(
        commands=[(ChangeName, ChangeNameHandler)], queries=[(ReadName, ReadNameHandler)]
    )
    provider = Provider()
    register_handlers(provider, registry, scope=Scope.APP)

    async def run() -> None:
        container = make_async_container(provider)
        try:
            mediator = Mediator(registry, container.get)
            assert await mediator.execute(ChangeName()) == "changed"
            assert await mediator.query(ReadName()) == "read"
        finally:
            await container.close()

    asyncio.run(run())
