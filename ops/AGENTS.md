
# Infrastructure and Delivery

## Structure

ops/ contains infrastructure definitions,
environment configuration and operational tooling.

Current tools include Terraform, Ansible, Docker
and CI/CD workflows.

Their organization may evolve as platform
provisioning capabilities develop.

## Responsibilities

Distinguish infrastructure used to operate
Developers-Hub from infrastructure provisioned
for developers through the platform.

DeveloperPlatform owns the business lifecycle
of developer-requested resources.

Infrastructure tooling implements the mechanisms
required to provision and manage those resources.

Avoid placing business decisions inside deployment
scripts or infrastructure definitions.

## Engineering Guidelines

- Select tools according to actual operational requirements.
- Consider reliability, security, cost and maintainability.
- Prefer reproducible and observable automation.
- Avoid duplicate configuration and unnecessary tooling.
- Evaluate state management, permissions and recovery.
- Consider infrastructure lifecycle and cleanup.
- Do not assume current hosting design is final.

## Execution

Use the execution method appropriate to the task.

Direct application execution, containers,
infrastructure provisioning and deployment
serve different purposes.

Do not require a specific tool unless necessary.

## Safety

- Protect credentials and infrastructure state.
- Verify target environments before live operations.
- Do not perform destructive operations without approval.
- Distinguish validation from successful deployment.
- Report actual verification and remaining risks.
