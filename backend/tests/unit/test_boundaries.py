"""Import contracts protect context/layer boundaries, including relative imports."""

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from api.app import create_app
from shared.infra.settings import Settings

BACKEND = Path(__file__).parents[2]
SRC = BACKEND / "src"
ROOTS = {"api", "identity", "devops_platform", "shared"}
CONTEXTS = {"identity", "devops_platform"}
RETIRED_ROOTS = {
    "containers",
    "entrypoints",
    "composition",
    "bootstrap",
    "provisioning",
    "platform_runtime",
    "platform_infrastructure",
    "developer_platform",
    "devops_hub",
    "infra",
}
IO_LIBRARIES = {
    "fastapi",
    "starlette",
    "pydantic",
    "pydantic_settings",
    "dishka",
    "sqlalchemy",
    "psycopg",
    "docker",
    "os",
    "pathlib",
    "subprocess",
    "socket",
    "hashlib",
    "hmac",
    "secrets",
}

# Cross-context dependencies of Platform persistence.
PROJECT_ACCESS_IMPORTS = {
    "devops_platform.infra.persistence.repositories.project_access": {
        "identity.domain.interfaces.project_access",
        "identity.domain.interfaces.project_access.IdentityProjectAccess",
        "identity.infra.persistence.models.user",
        "identity.infra.persistence.models.user.InternalUserRow",
    },
    "devops_platform.infra.persistence.resource_request_authority": {
        "identity.infra.persistence.models.user",
        "identity.infra.persistence.models.user.InternalUserRow",
    },
}


def imports(source, module, is_package=False):
    package = module if is_package else module.rpartition(".")[0]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = importlib.util.resolve_name("." * node.level + base, package)
            yield base
            # Include imported submodules/re-exports, not just the parent package.
            yield from (base + "." + alias.name for alias in node.names if alias.name != "*")


def context_name(module):
    if module == "identity" or module.startswith("identity."):
        return "identity"
    if module == "devops_platform" or module.startswith("devops_platform."):
        return "devops_platform"
    return None


def violation(module, target):
    if target in PROJECT_ACCESS_IMPORTS.get(module, ()):
        return False
    root = module.split(".")[0]
    other = target.split(".")[0]
    target_parts = target.split(".")
    module_parts = module.split(".")
    module_context = context_name(module)
    target_context = context_name(target)
    if other in RETIRED_ROOTS:
        return True
    if target == "shared.authorization" or target.startswith("shared.authorization."):
        return module_context is not None and module_parts[1:2] in (["application"], ["domain"])
    if module_context:
        layer_parts = module_parts[1:2]
        if module.startswith(module_context + ".infra.workers.") and other == "backend":
            return False
        if target in {
            "shared.application.interfaces.unit_of_work",
            "shared.application.interfaces.unit_of_work.UnitOfWork",
            "shared.application.interfaces.readiness",
            "shared.application.interfaces.readiness.ReadinessProbe",
        }:
            return False
        if target == "shared.dispatch" or target.startswith("shared.dispatch."):
            return False  # Pure cross-context message/handler contract.
        if (target_context is not None and target_context != module_context) or other in {
            "api",
            "backend",
            "containers",
            "entrypoints",
        }:
            return True
        if layer_parts in (["domain"], ["application"]) or module == "identity.contracts":
            if other == "shared" or "infra" in target_parts[1:]:
                return True
            if other in IO_LIBRARIES:
                return True
        if layer_parts == ["infra"]:
            if (target_context is not None and target_context != module_context) or other in {
                "api",
                "backend",
                "containers",
                "entrypoints",
            }:
                return True
            if other == "shared":
                return len(target_parts) > 1 and target_parts[1] != "infra"
            return False
        return False
    if root == "shared":
        return target_context is not None or other in {
            "api",
            "backend",
            "containers",
            "entrypoints",
        }
    if root == "api":
        if target in {
            "shared.application.interfaces.readiness",
            "shared.application.interfaces.readiness.ReadinessProbe",
        }:
            return False
        if target == "shared.dispatch" or target.startswith("shared.dispatch."):
            return False
        api_adapters = {
            "api.app",
            "api.health.metrics_adapter",
        }
        if module in api_adapters:
            is_context_infrastructure = target_context is not None and "infra" in target_parts
            if is_context_infrastructure or target.startswith("shared.infra."):
                return False
            if module == "api.app" and other == "backend":
                return False
            if (module in {"api.app", "api.health.metrics_adapter"}) and other in {
                "dishka",
                "sqlalchemy",
            }:
                return False
        return (
            other
            in {
                "shared",
                "backend",
                "containers",
                "entrypoints",
                "sqlalchemy",
                "psycopg",
                "docker",
            }
            or "infra" in target_parts[1:]
        )
    if root == "backend":
        http_bindings = ("api.health.metrics", "api.health.metrics_adapter", "api.settings.config")
        return other in {"containers", "entrypoints"} or (
            other == "api"
            and (
                module != "backend"
                or not any(
                    target == path or target.startswith(path + ".") or path.startswith(target + ".")
                    for path in http_bindings
                )
            )
        )
    return False


def test_source_import_contracts():
    actual_roots = {
        path.name for path in SRC.iterdir() if path.is_dir() and not path.name.startswith("__")
    }
    assert actual_roots == ROOTS
    assert not (SRC / "api" / "composition").exists()
    assert not (SRC / "developer_platform").exists()
    assert not (SRC / "devops_hub").exists()
    assert not any((SRC / root).exists() for root in RETIRED_ROOTS)
    assert not (SRC / "platform.py").exists(), (
        "src/platform.py would shadow Python's platform module"
    )
    import platform

    assert SRC not in Path(platform.__file__).resolve().parents
    for context in CONTEXTS:
        assert not (SRC / context / "infra" / "composition").exists()
        assert (SRC / context / "infra" / "module.py").is_file()
    sources = {"backend": ((SRC / "backend.py").read_text(), False)}
    for root in ROOTS:
        for path in (SRC / root).rglob("*.py"):
            parts = path.relative_to(SRC).with_suffix("").parts
            package = parts[-1] == "__init__"
            module = ".".join(parts[:-1] if package else parts)
            sources[module] = (path.read_text(), package)
    assert boundary_failures(sources) == []


def boundary_failures(sources):
    graph = {
        module: set(imports(source, module, package))
        for module, (source, package) in sources.items()
    }
    failures = []
    for origin in sources:
        visited = set()
        pending = list(graph[origin])
        while pending:
            target = pending.pop()
            if target in visited:
                continue
            visited.add(target)
            if violation(origin, target):
                failures.append(f"{origin} -> {target}")
            # Importing a child executes its package initializers. Follow their
            # reexports, but check ordinary modules as their own origins; treating
            # every transitive import as an import by the caller incorrectly makes
            # an HTTP adapter responsible for its dependencies' SQL imports.
            for package, (_, is_package) in sources.items():
                if is_package and (target == package or target.startswith(package + ".")):
                    pending.extend(graph[package])
            origin_context = context_name(origin)
            origin_parts = origin.split(".")
            origin_layer = origin_parts[1:2]
            if origin_context and origin_layer in (["domain"], ["application"]):
                pending.extend(graph.get(target, ()))
    return sorted(failures)


def test_indirect_package_reexport_cannot_smuggle_infrastructure_into_core():
    sources = {
        "identity": ("from .infra.security.opaque_secrets import PepperedTokenHasher", True),
        "identity.application.flow": ("from identity import PepperedTokenHasher", False),
        "identity.infra.security.opaque_secrets": ("import hmac", False),
    }
    failures = boundary_failures(sources)
    assert "identity.application.flow -> identity.infra.security.opaque_secrets" in failures
    assert "identity.application.flow -> hmac" in failures


@pytest.mark.parametrize(
    "module,source,forbidden",
    [
        ("identity.application.flow", "from ..infra import tokens", True),
        ("identity.application.flow", "from ..domain import credentials", False),
        ("identity.application.flow", "from shared.dispatch import Command", False),
        ("devops_platform.application.flow", "from identity import contracts", True),
        (
            "api.platform.resources.routes",
            "from devops_platform.infra import persistence",
            True,
        ),
        (
            "backend",
            "from devops_platform.infra import module",
            False,
        ),
        ("shared.infra.database", "import containers.http", True),
        ("identity.contracts", "from .infra import tokens", True),
        ("identity.infra.security.opaque_secrets", "from shared.infra import database", False),
        ("devops_platform.infra.persistence", "from identity.domain import records", True),
        ("identity.infra.persistence", "from .models import InternalUserRow", False),
        ("identity.infra.persistence", "import sqlalchemy", False),
        ("identity.infra.persistence", "from datetime import datetime", False),
        ("identity.infra.persistence", "import shared", False),
        ("identity.infra.persistence", "from shared.domain import value", True),
        ("identity.infra.persistence", "from api import errors", True),
        ("identity.infra.persistence", "from backend import settings", True),
    ],
)
def test_checker_resolves_relative_imports_and_reexports(module, source, forbidden):
    assert any(violation(module, target) for target in imports(source, module)) is forbidden


def test_application_packages_import_without_frameworks_or_other_contexts():
    # Independent interpreters prevent previously loaded modules from hiding a leak.
    for context in ("identity", "devops_platform"):
        script = """
import importlib.abc,sys
sys.path.insert(0,sys.argv[1])
class DenyIO(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if any(
            fullname == name or fullname.startswith(name + ".")
            for name in sys.argv[3].split(",")
        ):
            raise AssertionError('Forbidden dependency: '+fullname)
sys.meta_path.insert(0,DenyIO())
if sys.argv[2]=='identity':
    import identity.application.api_tokens.authenticate_api_token.handler
    import identity.application.api_tokens.manage_personal_tokens
    import identity.application.api_tokens.revoke_api_token.handler
else:
    import devops_platform.application.resource_management.catalog.handler,devops_platform.domain
"""
        denied = IO_LIBRARIES | (CONTEXTS - {context})
        subprocess.run(
            [sys.executable, "-I", "-c", script, str(SRC), context, ",".join(sorted(denied))],
            check=True,
            capture_output=True,
            text=True,
        )


def test_public_openapi_matches_versioned_ledger_contract():
    expected = json.loads((BACKEND / "tests/contracts/openapi.json").read_text())
    settings = Settings(
        database_url="postgresql+psycopg://localhost:1/devops_hub_test",
        token_pepper="baseline-test-pepper-" * 3,
    )
    assert create_app(settings).openapi() == expected


def test_initial_migration_is_explicit_snapshot():
    source = (BACKEND / "migrations/versions/0001_initial_schema.py").read_text()
    assert source.count("op.create_table(") == 25
    assert "op.drop_table(" in source
    assert "create_all(" not in source
    assert "drop_all(" not in source
    assert "registered_metadata" not in source
