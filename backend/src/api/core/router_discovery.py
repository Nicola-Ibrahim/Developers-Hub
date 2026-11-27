"""Mount routers exported by API feature packages."""

from collections.abc import Iterator, Mapping, Sequence
from importlib import import_module
from importlib.util import find_spec
from pkgutil import iter_modules
from types import ModuleType
from typing import Literal

from fastapi import APIRouter, FastAPI
from fastapi.params import Depends

type _RouterExport = Literal["standalone_router", "router"]
_EXPORTS: tuple[_RouterExport, ...] = ("standalone_router", "router")


def mount_discovered_routes(
    target: FastAPI | APIRouter,
    packages: Sequence[str],
    *,
    prefix: str = "",
    dependencies_by_package: Mapping[str, Sequence[Depends]] | None = None,
) -> None:
    """Mount each package's feature routers, applying its dependencies to `router` exports."""
    configured_dependencies = dependencies_by_package or {}
    for package_name in packages:
        package = import_module(package_name)
        for export, router in _discover_routers(package):
            dependencies = configured_dependencies.get(package_name) if export == "router" else None
            target.include_router(router, prefix=prefix, dependencies=dependencies)


def _discover_routers(package: ModuleType) -> Iterator[tuple[_RouterExport, APIRouter]]:
    """Yield routers from immediate feature packages in module name order."""
    for feature in sorted(iter_modules(package.__path__), key=lambda item: item.name):
        if not feature.ispkg or feature.name.startswith("_"):
            continue
        module_name = f"{package.__name__}.{feature.name}.routes"
        if find_spec(module_name) is None:
            continue
        module = import_module(module_name)
        found = False
        for export in _EXPORTS:
            if not hasattr(module, export):
                continue
            router = getattr(module, export)
            if not isinstance(router, APIRouter):
                raise TypeError(f"{module_name}.{export} must be an APIRouter")
            found = True
            yield export, router
        if not found:
            raise TypeError(f"{module_name} must export router or standalone_router")
