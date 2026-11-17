---
name: backend-development
description: Consolidate or refactor an existing Developers-Hub backend use case across handlers, domain rules and repository ports.
---

# Backend use-case refactor

Use for backend refactoring or a new business use case
spanning multiple layers. Not every Python edit.

## Procedure

1. Start with the requested observable behavior.

2. Trace all relevant entry points:
   - HTTP, worker, operator or CLI
   - Command/query registration
   - Application handler
   - Domain entity, aggregate or policy
   - Repository port
   - Persistence or provider adapter
   - Existing tests

3. Classify each operation as:
   - Public business use case
   - Trusted operator use case
   - Internal workflow step
   - Confirmed duplicate or dead code

4. Choose one clear application orchestration path.

   Internal checks may be ordinary methods or functions.
   Do not generate a command/handler pair for every helper.
   Do not introduce aggregates without meaningful invariants.

5. Preserve:
   - Authentication and authorization
   - Sessions and CSRF protection
   - Credential security
   - Transaction boundaries
   - Optimistic concurrency
   - Idempotency and retry behavior
   - Worker recovery and cleanup

6. Remove obsolete code only after migrating all callers,
   DI registrations, tests and imports.

7. Run focused tests first.
   Use disposable infrastructure for integration tests.

## Useful search examples

```bash
rg 'LoginCommand|LoginHandler|BrowserIdentityService' backend/src backend/tests

rg 'RegisterProjectCommand|CreateApplication|ApplicationDelivery' backend/src backend/tests