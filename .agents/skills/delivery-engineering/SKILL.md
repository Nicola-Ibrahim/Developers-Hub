---
name: delivery-engineering
description: Change or verify a Developers-Hub CI pipeline, Docker runtime, infrastructure plan, or deployment/rollback workflow.
---

# Delivery and infrastructure workflow

Use when changing operational automation or validating
a deployment path.

## Procedure

1. Identify what the task actually concerns:
   - Direct Python execution
   - Docker/container runtime
   - CI validation
   - Artifact publishing
   - Infrastructure provisioning
   - Application deployment

2. Do not treat these operations as interchangeable.

3. Follow the execution mode requested by the user
   unless a genuine dependency requires another mode.

   A focused Python unit test does not require Docker.
   Real Docker-provider acceptance does require Docker.

4. Trace the delivery chain where applicable:

   Source revision
     -> Tests and build
     -> Immutable artifact
     -> Approved deployment target
     -> Health and readiness
     -> Rollback or cleanup

5. Identify which stages are already implemented
   and which remain planned.

6. Preserve:
   - Credential security
   - Target isolation
   - Infrastructure state ownership
   - Least-privilege permissions
   - Idempotency
   - Retry and recovery
   - Resource ownership labels

7. Validate locally or through static checks first.

   Terraform plan is not proof of deployment.
   Image publishing is not application deployment.

8. Do not apply Terraform, deploy, modify live secrets,
   destroy resources or run global Docker cleanup
   without specific authorization.

## Handoff

Report:
- Exact stage verified
- Commands and actual results
- Missing prerequisites
- Rollback/recovery gaps

Consult ops/AGENTS.md and docs/operations.md
only for tasks involving those systems.