---
name: system-design
description: Analyze architectural boundaries, domain models, system interactions, and substantial design changes.
---

# System Design

## Procedure

1. Understand the business problem and desired outcome.

2. Investigate the current implementation and relevant constraints.

3. Identify:
   - Business capabilities and domain concepts
   - Ownership and responsibilities
   - Consistency and lifecycle boundaries
   - Dependencies and external interactions
   - Existing design problems and unnecessary complexity

4. Compare reasonable alternatives using:
   - Correctness
   - Cohesion and coupling
   - Maintainability
   - Scalability where required
   - Operational complexity

5. Recommend the simplest design that satisfies the requirements.

6. Define clear boundaries, contracts, and an incremental
   implementation approach when needed.

## Principles

- Do not treat existing architecture as automatically correct.
- Do not introduce bounded contexts, aggregates, services,
  or interfaces without justified responsibilities.
- Distinguish business concepts from implementation details.
- Avoid speculative abstractions and premature optimization.
- Prefer concise diagrams and explanations.
- Keep decisions in the current conversation unless durable
  documentation is necessary.