---
name: api-development
description: Design, implement, refactor, or review API endpoints, contracts, and integrations.
---

# API Development

## Procedure

1. Identify the consumer, requested operation, and expected result.

2. Inspect existing routes, schemas, callers, and application logic.

3. Evaluate:
   - Contract correctness and consistency
   - Input validation
   - Authentication and authorization where applicable
   - Error handling
   - Duplicate endpoints or responsibilities
   - Compatibility and integration requirements

4. Design a clear API contract using existing conventions
   where appropriate.

5. Implement the necessary changes without duplicating
   business logic across layers.

6. Verify successful, invalid, and relevant failure scenarios.

## Principles

- Do not prescribe a particular authentication mechanism.
- Do not assume existing API contracts are correctly designed.
- Separate transport concerns from business responsibilities.
- Avoid unnecessary endpoints and abstraction layers.
- Identify intentional breaking changes explicitly.
- Report verification results concisely.