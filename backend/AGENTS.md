
# Backend

## Technology

Current stack: Python 3.12+, FastAPI, SQLAlchemy,
PostgreSQL, Alembic, Dishka, pytest, Ruff and mypy.

These describe the existing implementation, not
mandatory technologies for every future component.

## Structure

backend/src/
├── api/              # HTTP endpoints and schemas
├── identity/         # Identity bounded context
│   ├── domain/
│   ├── application/
│   └── infra/
├── devops_platform/  # DeveloperPlatform bounded context
│   ├── domain/
│   ├── application/
│   └── infra/
├── composition/      # Dependency wiring and integrations
└── shared/           # Shared technical components

This is the current high-level structure.
Adapt it when an approved design requires changes.

## Domain Architecture

The current system uses a modular monolith with
Identity and DeveloperPlatform bounded contexts.

Current design direction:

Identity:

- Accounts and credentials
- Authentication and sessions
- API credentials and tokens

DeveloperPlatform:

- Projects and applications
- Project membership and access
- Environments and software delivery
- Infrastructure resource management

Some responsibilities are still being migrated from
the existing implementation.

These boundaries are architectural decisions that
may be reconsidered when business requirements change.

## Layer Responsibilities

Prefer clear separation of concerns:

- Domain: business concepts, rules and invariants.
- Application: use cases and workflow coordination.
- Infrastructure: persistence and external adapters.
- API: transport and request/response handling.
- Composition: dependency wiring and integration.

Dependencies should generally point toward business logic.

Avoid coupling domain models to infrastructure details.
Justify intentional deviations when they improve the design.

## DDD Modeling

Use DDD where its concepts provide real value.

- Identify aggregates through consistency boundaries.
- Keep entities and value objects with their owning models.
- Organize code by aggregate or business capability when useful.
- Put business invariants close to their responsible model.
- Reference other aggregates by identity when appropriate.
- Avoid aggregates, services and interfaces without clear purpose.

Do not force folder layouts or patterns merely for consistency.

## Application Use Cases

- Organize operations around meaningful business capabilities.
- Give each workflow clear responsibility and ownership.
- Prefer cohesive orchestration over unnecessary delegation.
- Use commands, queries and handlers when beneficial.
- Internal operations need not become separate use cases.
- Avoid duplicate logic, forwarding layers and redundant contracts.

Existing patterns may be consolidated, replaced or redesigned
when justified by the requirements.

## Persistence

Prefer persistence boundaries aligned with the domain model.

Typical organization:

infra/persistence/
├── repositories/     # Persistence implementations
├── models/           # Internal ORM mappings and tables
└── queries/          # Optional read projections

- Keep ORM models separate from domain models.
- Prefer aggregate-oriented write repositories.
- Do not create repositories for every database table.
- Use dedicated read queries or projections where useful.
- Define transaction ownership explicitly.
- Consider consistency, concurrency and performance needs.

This structure is guidance, not a required folder template.

## Design and Refactoring

When implementing or redesigning a feature:

1. Understand the business requirements.
2. Trace relevant existing behavior and dependencies.
3. Identify incorrect assumptions and design problems.
4. Compare reasonable alternatives when necessary.
5. Choose the simplest justified solution.
6. Implement and verify the agreed scope.

Actively identify:

- Duplicated responsibilities
- Unnecessary abstraction
- Misplaced domain logic
- Incorrect aggregate boundaries
- Tight coupling
- Obsolete code
- Missing or inconsistent behavior

Do not preserve bad architecture solely for compatibility.
Do not introduce unnecessary replacement abstractions.

Assess breaking changes and security implications explicitly.

## Correctness

Evaluate relevant requirements for:

- Security and authorization
- Data consistency and transactions
- Concurrency and race conditions
- Idempotency and recovery
- Failure handling and observability
- Resource ownership and cleanup

Choose appropriate mechanisms for the actual problem.

Do not mandate specific authentication methods,
token formats, infrastructure tools or design patterns
without a concrete requirement.

## Verification

From backend/, using the configured environment:

.venv/bin/ruff check src tests migrations
.venv/bin/ruff format --check src tests migrations
.venv/bin/mypy src
.venv/bin/pytest -q -m 'not postgres'

Run focused checks before broader verification.

Use isolated resources for integration testing.
Report actual results and unverified behavior.

## Working Principles

- Current requirements take precedence over old design preferences.
- Explain important conflicts rather than ignoring requests.
- Do not assume historical documents are authoritative.
- Keep changes coherent and avoid unrelated expansion.
- Use agents and skills selectively.
- Avoid unnecessary planning files and repeated investigations.
