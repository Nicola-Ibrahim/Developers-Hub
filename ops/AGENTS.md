# Infrastructure and Delivery

## Structure

- ops/local/ansible/: local bootstrap
- ops/hosting/: host configuration and Terraform
- ../compose.yaml: container orchestration
- ../scripts/dev.sh: local platform commands
- ../.github/workflows/: CI/CD

## Ownership

- Terraform: infrastructure provisioning
- Ansible: host configuration
- CI/CD: build, publish and release workflow
- Docker/Compose: container runtime
- Platform workers: resource and application lifecycle

Do not move domain business logic into infrastructure tools.

## Execution

Choose execution mode based on the task.
Direct Python, Docker and Compose are not interchangeable,
and none should be forced unnecessarily.

Local commands from repository root:

scripts/dev.sh help
scripts/dev.sh status
scripts/dev.sh up
scripts/dev.sh down

Resource/application worker profiles are optional.
Inspect the script before using additional options.

## Safety

- No secrets in code, logs, plans or build artifacts.
- Use immutable image identities for releases.
- Publishing an image is not deploying it.
- Verify readiness separately from container startup.
- Preserve ownership labels, state and rollback behavior.
- Do not provision or destroy live resources without approval.
