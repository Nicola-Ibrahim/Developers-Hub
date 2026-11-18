
# Developers-Hub

## Product

Developers-Hub is an Internal Developer Platform (IDP)
for managing projects, applications, environments,
software delivery, and infrastructure resources.

The platform aims to simplify development workflows,
repository integration, deployment, and provisioning.

## Repository

- backend/: Python API, domain logic, persistence, workers
- frontend/: Next.js developer portal
- ops/: Infrastructure definitions and operational tooling
- scripts/: Development and maintenance utilities
- .github/workflows/: CI/CD automation
- docs/: Architecture, requirements and guides

Consult component AGENTS.md files when working in
their directories.

## Engineering Approach

- Understand the requested outcome before changing code.
- Inspect relevant implementation and its dependencies.
- Evaluate existing design critically rather than copying it.
- Prefer simple, cohesive and maintainable solutions.
- Identify duplication, unnecessary abstraction and poor ownership.
- Choose technologies and patterns based on actual requirements.
- Avoid speculative complexity and unrelated refactoring.
- Verify important assumptions and affected behavior.

## Architecture Evolution

Existing architecture is a starting point, not a permanent rule.

When the user requests a new design:

- Reevaluate existing boundaries and assumptions.
- Consider alternatives and explain important trade-offs.
- Prefer the newly agreed design over outdated conventions.
- Update affected architecture guidance when the design changes.
- Do not silently implement an older design instead.

Distinguish current implementation, agreed target design,
and future possibilities.

Source code shows existing behavior. Documentation may
be outdated and should not override agreed requirements.

## Safety and Changes

- Preserve unrelated user changes.
- Identify security, data integrity and compatibility impacts.
- Never expose secrets or credentials.
- Avoid destructive or live operations without authorization.
- Do not silently introduce security or data-loss regressions.
- Run relevant checks and report actual verification.

## Codex Workflow

- The current conversation defines the active task.
- Use targeted investigation and keep context relevant.
- Delegate only when a separate agent adds value.
- Skills provide optional reusable procedures.
- Avoid mandatory long plans or unnecessary documentation.
- Keep handoffs concise and evidence-based.
- Optimize for correctness and total token consumption.
