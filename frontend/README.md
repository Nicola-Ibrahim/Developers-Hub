# 🖥️ Developers-Hub Dashboard

**A single workspace for developers to manage projects, applications and temporary infrastructure.**

`Next.js 16` · `React 19` · `TypeScript` · `App Router` · `CSS`

[Project overview](../README.md) · [Backend API](../backend/README.md) · [C4 architecture](../docs/architecture.md)

---

## What developers see

| Workspace | Capability |
| --- | --- |
| **Overview** | Active project and workspace summary |
| **Resources** | Request databases, inspect status, extend leases, reveal connections and delete |
| **Applications** | Create applications, manage previews, attach databases and deploy approved images |
| **Account & team** | Sign in, change passwords, manage sessions and authorized project memberships |
| **Activity** | Project-scoped operation history |
| **Guest demo** | Synthetic, read-only workspace at `/demo` — no backend access required |

## Frontend architecture

The browser accesses FastAPI through a **same-origin Next.js API proxy**. Next.js owns presentation and session-aware navigation; the backend remains responsible for authorization and infrastructure state.

```mermaid
flowchart LR
    Browser["Browser"] --> Pages["Next.js App Router"]

    subgraph UI["Dashboard"]
        Pages --> Workspace["Workspace state / active project"]
        Workspace --> Features["Resources, applications, identity"]
        Features --> Proxy["Same-origin API proxy"]
    end

    Proxy --> API["FastAPI backend"]
    API --> DB[("PostgreSQL")]
    API --> Policy["OPA authorization"]
```

### Key UI boundaries

- **Identity:** the server manages an HttpOnly session cookie; browser mutations use an in-memory CSRF token.
- **Project switching:** the workspace provider resets or rejects stale state after user/project changes.
- **Secrets:** resource connection credentials are requested only when the user opens the connection view.
- **Permissions:** the UI reflects allowed operations but never replaces backend authorization checks.
- **Progress:** current resource/application views use periodic status refreshes. **SSE-only progress is planned**, not implemented.

## Run locally

Requires Node.js 22+, npm and a reachable backend. From `frontend/`:

```bash
npm ci
BACKEND_URL=http://127.0.0.1:8000 npm run dev
```

Open `http://127.0.0.1:3000`. `BACKEND_URL` is server-side only; use `http://api:8000` inside Docker Compose (see [`.env.example`](.env.example)). Configure the backend's allowed browser origins for authenticated mutations.

To run the complete core stack from the repository root, use:

```bash
./scripts/dev.sh up
```

The demo is available without an account. Actual infrastructure actions require an operator-created account, authorized project and enabled provider.

## Code map

| Concern | Location |
| --- | --- |
| Routes, layouts and page boundaries | [`src/app/`](src/app/) |
| Active session and project | [`src/features/workspace/`](src/features/workspace/) |
| Resource lifecycle UI | [`src/features/resources/`](src/features/resources/) |
| Application and deployment UI | [`src/features/applications/`](src/features/applications/) |
| Sign-in and administration | [`src/features/identity/`](src/features/identity/) |
| API proxy | [`src/app/api/v1/`](src/app/api/v1/) |
| Shared styles | [`src/app/globals.css`](src/app/globals.css) |

## Verify

```bash
npm run typecheck
npm run build
node --test tests/client.test.mjs
```

**Known issue in the reviewed revision:** components import `src/lib/api/client` and `src/lib/api/pagination`, but those shared modules are missing from the committed tree. Restore them before expecting the TypeScript check or build to pass.

---

For server-side contracts, security and provisioning workflows, see the [Backend README](../backend/README.md).
