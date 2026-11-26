# Backend documentation and diagrams

This directory contains backend-specific architecture diagrams. The service overview, setup and operational notes remain in the [backend README](../README.md). Cross-system context and container views remain in [shared documentation](../../docs/README.md), and transaction and bounded-context details are in the [architecture deep dive](../../docs/architecture.md).

| View | Editable source | Preview | Scope |
| --- | --- | --- | --- |
| Backend components | [draw.io](diagrams/backend-components.drawio) | [SVG](diagrams/backend-components.svg) | FastAPI modules, composition, persistence and workers |
| Provisioning lifecycle | [draw.io](diagrams/provisioning.drawio) | [SVG](diagrams/provisioning.svg) | Durable resource operations and worker effects |
| Image delivery | [draw.io](diagrams/image-delivery.drawio) | [SVG](diagrams/image-delivery.svg) | CI image publishing and release boundary |
| Backend hosting | [draw.io](diagrams/aws-backend.drawio) | [SVG](diagrams/aws-backend.svg) | Optional Terraform server placement, not a live deployment |

Edit the `.drawio` source and keep its SVG preview synchronized. See [documentation maintenance guidance](../../docs/AGENTS.md).

## Supporting illustrations

These SVG illustrations describe Ansible-based hosting and deployment concepts. They are contextual assets, not authoritative deployment diagrams; use the editable AWS hosting diagram and current [Terraform instructions](../../ops/hosting/terraform/README.md) for the repository's actual hosting definition.

- [Ansible in CI/CD](images/ansible.svg)
- [SSH deployment compared with Ansible](images/deploy_with_ansible.svg)
