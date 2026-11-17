# Developers-Hub

## Product

Internal Developer Platform for team-owned projects containing
independently deployable applications, repositories, environments,
CI/CD workflows, deployments, and managed resources.

## Repository map

- backend/: FastAPI modular monolith and workers
- frontend/: Next.js developer portal
- ops/: Terraform, Ansible and hosting configuration
- .github/workflows/: CI/CD
- scripts/: local development utilities
- docs/: architecture, requirements and operational guidance

## Architecture

Two bounded contexts:

- Identity: accounts, credentials, sessions, tokens,
  and currently project membership
- DeveloperPlatform: Project & Application Management,
  Software Delivery, Resource Management

Do not create new bounded contexts without a justified
business boundary.

## Working rules

- Inspect relevant code and callers before editing.
- Prefer the smallest coherent change.
- Avoid duplicate abstractions, handlers and interfaces.
- Do not assume code is unused without checking references.
- Preserve unrelated working-tree changes.
- Delegate only when useful; no mandatory agent sequence.
- Use planning documents only when they add lasting value.
- Verify changes with focused tests.
- Report actual results and unverified behavior.

## Safety

Preserve authorization, transactions, resource ownership,
idempotency, recovery and secret protection.

No live deployment, destructive cleanup, shared-data migration,
secret changes, staging or committing without authorization.

## Additional guidance

- backend/AGENTS.md
- frontend/AGENTS.md
- ops/AGENTS.md

Consult docs/architecture.md for cross-component changes.
Treat documentation as intent, not proof of implementation.
