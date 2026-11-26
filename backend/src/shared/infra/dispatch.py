"""Use a message registry to register constructor-injected handlers with Dishka."""

from collections.abc import Callable, Collection, Mapping
from importlib import import_module
from pkgutil import walk_packages
from types import ModuleType
from typing import Any

from dishka import Provider, Scope

from shared.dispatch import Command, HandlerRegistry, Query, RegistrationError


def register_handlers(
    provider: Provider,
    registry: HandlerRegistry,
    *,
    scope: Scope,
    messages: Collection[type[object]] | None = None,
    exclude_messages: Collection[type[object]] = (),
    factories: Mapping[type[object], Callable[..., Any]] | None = None,
) -> None:
    handlers = dict.fromkeys(
        handler
        for message, handler in (*registry.commands.items(), *registry.queries.items())
        if (messages is None or message in messages) and message not in exclude_messages
    )
    factories = factories or {}
    if factories.keys() - handlers.keys():
        raise RegistrationError("A handler factory has no message registration")
    for handler in handlers:
        provider.provide(factories.get(handler, handler), provides=handler, scope=scope)


def validate_context_messages(
    registry: HandlerRegistry,
    application: ModuleType,
    *,
    internal: Collection[type[object]] = (),
) -> None:
    """Find messages declared in the application package, including unregistered modules."""
    for entry in walk_packages(application.__path__, application.__name__ + "."):
        module = import_module(entry.name)
        registry.require_messages(
            value
            for value in vars(module).values()
            if isinstance(value, type)
            and issubclass(value, (Command, Query))
            and value.__module__ == entry.name
            and value not in internal
        )
