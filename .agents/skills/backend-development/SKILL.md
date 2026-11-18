---
name: backend-development
description: Design, implement, refactor, or review backend behavior, domain models, application use cases, and persistence.
---

# Backend Development

## Procedure

1. Understand the requested behavior and business requirements.

2. Inspect relevant implementation, entry points, dependencies,
   callers, and tests. Use targeted searches.

3. Critically evaluate the current design:
   - Incorrect or missing behavior
   - Duplicate responsibilities and logic
   - Unnecessary abstractions or forwarding layers
   - Misplaced business rules
   - Poor aggregate or transaction boundaries
   - Unused code and interfaces

4. Identify the simplest coherent design that satisfies
   the requirements. Challenge existing patterns when necessary.

5. Implement within the agreed scope:
   - Keep responsibilities clearly owned.
   - Introduce abstractions only when justified.
   - Reuse existing code when appropriate.
   - Remove obsolete code after verifying dependencies.
   - Respect applicable architectural boundaries.

6. Verify correctness:
   - Test expected behavior and important failure cases.
   - Check affected integrations and callers.
   - Run relevant static checks.

7. Report changes, decisions, verification, and remaining risks.

## Principles

- Existing code is evidence, not architectural authority.
- Do not preserve incorrect behavior merely for compatibility.
- Do not rewrite correct behavior without a reason.
- Do not force particular patterns, frameworks, or mechanisms.
- Evaluate security, consistency, and concurrency where relevant.
- Prefer focused changes over speculative architecture.
- Escalate material contract or behavioral changes outside scope.
- Do not create unnecessary plans, files, or abstractions.