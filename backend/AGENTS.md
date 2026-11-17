# Backend

Stack: Python 3.12+, FastAPI, SQLAlchemy, PostgreSQL,
Alembic, Dishka, pytest, Ruff and mypy.

## Structure

src/
├── api/              # HTTP routes, schemas, security
├── identity/         # Identity bounded context
│   ├── domain/
│   ├── application/
│   └── infra/
├── devops_platform/  # DeveloperPlatform bounded context
│   ├── domain/
│   ├── application/
│   └── infra/
├── composition/      # Process-level DI and integrations
└── shared/           # Shared technical infrastructure

## DDD boundaries

- Domain: pure business rules and invariants.
- Application: business use cases and orchestration.
- Infrastructure: repositories, adapters and providers.
- API: HTTP authentication and request/response mapping.
- Composition: dependency injection and process setup.

Dependency direction: API → Application → Domain.
Infrastructure implements inward-facing interfaces.

Do not import FastAPI, SQLAlchemy or Dishka into domain code.

## Use-case conventions

- One meaningful business operation per use case.
- Internal helpers do not require command/handler wrappers.
- Aggregates exist to protect consistency boundaries.
- Repositories represent aggregates or coherent operations.
- Trace every caller before consolidating or deleting code.
- Preserve public contracts unless change is authorized.

## Invariants

- Operation hosts own transaction completion.
- Keep password hashing outside long-running DB transactions.
- Preserve session, CSRF, token and permission protections.
- External provider effects follow durable committed intent.
- Preserve idempotency, ownership, retries and recovery.
- Alembic owns schema migrations.

## Verification

From backend/ with the local virtual environment:

.venv/bin/ruff check src tests migrations
.venv/bin/ruff format --check src tests migrations
.venv/bin/mypy src
.venv/bin/pytest -q -m 'not postgres'

Run relevant focused tests first.
PostgreSQL/Docker acceptance requires isolated test resources.
Do not infer real provider readiness from unit tests.
