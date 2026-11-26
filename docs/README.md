# Shared architecture documentation

This folder contains cross-system architecture documentation. Component-specific documentation and diagrams live with their applications: [backend](../backend/docs/README.md) and [frontend](../frontend/docs/README.md). Editable `.drawio` files are the source of truth; adjacent SVG files are previews. Open a source in [diagrams.net](https://app.diagrams.net/) or draw.io Desktop.

| View | Source | Preview | Scope |
| --- | --- | --- | --- |
| C4 Level 1 — System context | [draw.io](c4/system-context.drawio) | [SVG](c4/system-context.svg) | Current logical model |
| C4 Level 2 — Containers | [draw.io](c4/containers.drawio) | [SVG](c4/containers.svg) | Current logical model |
| C4 Level 3 — Backend components | [draw.io](../backend/docs/diagrams/backend-components.drawio) | [SVG](../backend/docs/diagrams/backend-components.svg) | Current logical model |
| C4 Level 3 — Frontend components | [draw.io](../frontend/docs/diagrams/frontend-components.drawio) | [SVG](../frontend/docs/diagrams/frontend-components.svg) | Current logical model |
| AWS backend deployment | [draw.io](../backend/docs/diagrams/aws-backend.drawio) | [SVG](../backend/docs/diagrams/aws-backend.svg) | Optional infrastructure and illustrative runtime placement |
| Frontend hosting | [draw.io](../frontend/docs/diagrams/frontend-hosting.drawio) | [SVG](../frontend/docs/diagrams/frontend-hosting.svg) | Proposed alternatives, not simultaneous deployments |
| Provisioning lifecycle | [draw.io](../backend/docs/diagrams/provisioning.drawio) | [SVG](../backend/docs/diagrams/provisioning.svg) | Current durable workflow |
| CI / image publishing | [draw.io](../backend/docs/diagrams/image-delivery.drawio) | [SVG](../backend/docs/diagrams/image-delivery.svg) | Existing conditional workflow and inactive proposed release path |

## Maintain the diagrams

1. Review relevant source code, Compose and infrastructure configuration whenever an architectural change is made.
2. Update affected `.drawio` files in shared `docs/`, `backend/docs/diagrams/` or `frontend/docs/diagrams/`. Shapes, labels and connectors are editable; XML is intentionally uncompressed for version control.
3. Export each affected diagram as SVG with a white background, cropping to the diagram (or using the existing page dimensions). Replace its adjacent `.svg` file. Do not edit previews separately.
4. Review the rendered diagrams for crossings, clipping, stale labels and accurate status markers. Commit the source and preview in the same pull request.
5. Update affected README descriptions and `docs/architecture.md` when architectural semantics change.

Example draw.io Desktop CLI (adjust executable path for your OS):

```sh
drawio --export --format svg --output docs/c4/system-context.svg docs/c4/system-context.drawio
```

The command is illustrative; use your installed application's export help or graphical Export as SVG menu if the CLI differs.

## Modeling conventions

- Standard C4 numbering: Level 1 context, Level 2 containers, Level 3 components. Earlier discussions used Level 0/1 for the first two.
- Frontend and backend are different deployable applications. Identity and DeveloperPlatform are modules in the same API, not microservices.
- Blue: data / application boundaries; teal: application behavior; purple: frontend / identity; orange: jobs / hosting; gray: supporting systems.
- Deployment views distinguish infrastructure definitions from actual runtime deployment. The current optional Terraform target is EC2, not ECS/RDS. The frontend hosting options are alternatives.
- These diagrams use editable technology-name badges and native shapes, rather than licensed icon packs or external images.
- Initial SVGs were rendered from the same geometry as the native draw.io XML; they are not exports produced by the draw.io Desktop application. Re-export after editing.
