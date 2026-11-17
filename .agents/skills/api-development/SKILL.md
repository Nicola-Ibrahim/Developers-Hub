---
name: api-development
description: Change or verify a Developers-Hub FastAPI endpoint, including its request schema, permissions and compatibility.
---

# FastAPI contract change

Use when HTTP behavior changes or when auditing
API-to-use-case wiring.

## Procedure

1. Identify:
   - HTTP method and path
   - Request/response schemas
   - Authentication source
   - Permission decision
   - Expected status codes and errors

2. Trace the route through the context module to the
   owning application use case.

3. Keep domain mutations and direct ORM operations
   out of API routes.

4. Clarify:
   - Authorization
   - Idempotency
   - API compatibility
   - Error mapping
   - Sensitive credential disclosure

5. Change only the required routes, schemas,
   module wiring and dependent callers.

6. Avoid duplicating checks without a clear
   security or ownership reason.

7. Test:
   - Successful request
   - Invalid input
   - Denied access
   - Relevant failure path
   - Retry behavior when applicable

8. Compare API/OpenAPI contracts where compatibility
   with existing clients matters.

## Handoff

Report:
- HTTP behavior changed
- Compatibility preserved
- Authentication/authorization impact
- Tests performed and remaining gaps

If domain meaning changes, return the decision
to the coordinator before implementation.