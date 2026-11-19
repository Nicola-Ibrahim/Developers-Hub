# Developers-Hub · Architecture deep dive

[← Project overview](../README.md)

Developers-Hub is a **DDD-inspired modular monolith** with a FastAPI control-plane API, separately running workers, and a shared PostgreSQL database. Its central concern is the boundary between **transactional control-plane state** and **long-running external effects**.

The [README](../README.md#architecture) contains the **C4 Level 1 system context** and **Level 2 container** diagrams. This document zooms into the API application (Level 3), then shows its database/worker lifecycle.

## C4 Level 3: Control-plane API components

*Components inside the FastAPI application container (not individually deployed services).*

```mermaid
flowchart TB
    Browser["Next.js dashboard<br/>HTTP client"]
    OPA["OPA policy service<br/>External to API process"]
    DB[("PostgreSQL<br/>External to API process")]

    subgraph API["FastAPI control-plane API · Python process"]
        Routes["HTTP routes and schemas<br/>Transport mapping and validation"]
        Boundary["API composition / platform request boundary<br/>Credentials, authorization and transactions"]
        Identity["Identity module<br/>Accounts, credentials and sessions"]
        Platform["DeveloperPlatform module<br/>Projects, access, resources and delivery"]
        Dispatch["Typed module dispatch<br/>Command/query handler resolution"]
        Domain["Domain models and policies<br/>Invariants and state transitions"]
        Persistence["SQLAlchemy adapters<br/>Repositories and projections"]
        DI["Dishka composition<br/>Providers and execution scopes"]
    end

    Browser -->|Requests| Routes
    Routes -->|Delegates| Boundary
    Boundary -->|Identity operations| Identity
    Boundary -->|Platform operations| Dispatch
    Dispatch -->|Invokes| Platform
    Platform -->|Enforces invariants| Domain
    Identity -->|Persists| Persistence
    Platform -->|Persists| Persistence
    Persistence -->|SQL| DB
    Boundary -->|Evaluates identity permissions| OPA
    DI -.->|Resolves dependencies| Identity
    DI -.->|Resolves dependencies| Platform
    DI -.->|Provides transaction sessions| Persistence
```

The diagram shows logical components and dependencies; it is **not a claim that every use case currently follows an identical dispatcher pipeline**. Platform HTTP operations use Dishka `ACTION` scopes; some Identity workflows retain specialized transaction handling.

## Bounded-context responsibilities

| Context | Owns | In the code |
| --- | --- | --- |
| **Identity** | Users, credentials, API tokens, browser sessions, authentication and session security | [`backend/src/identity/`](../backend/src/identity/) |
| **DeveloperPlatform** | Projects, project membership and authorization, resource admission/leases, operations, application delivery | [`backend/src/devops_platform/`](../backend/src/devops_platform/) |
| **Composition** | HTTP adaptation, cross-context integration, Dishka registration, transaction boundary assembly | [`backend/src/api/`](../backend/src/api/) and [`backend/src/composition/`](../backend/src/composition/) |

The two contexts share a PostgreSQL control-plane database. Their separation is primarily **code, ownership, and domain behavior**, not separate databases or deployments.

## Transaction model

### Ordinary API operations

```mermaid
sequenceDiagram
    participant Route as FastAPI route
    participant Host as Platform request boundary
    participant Action as Dishka ACTION scope
    participant Handler as Application handler
    participant DB as PostgreSQL

    Route->>Host: Command / query
    Host->>Action: Create operation scope
    Action->>DB: Begin transaction
    Host->>DB: Revalidate authorization as required
    Action->>Handler: Resolve and execute
    Handler->>DB: Repository reads / writes
    Action->>DB: Commit or rollback
    Action-->>Route: Materialized result
```

The module boundary owns the **normal atomic platform operation**, while SQLAlchemy supplies the actual database transaction. A request may contain multiple separate operations; an HTTP connection is **not** automatically one long transaction.

### Multi-phase work

Login, credential-file delivery, and infrastructure workers can require specialized boundaries. A successful first phase cannot be undone by rolling back a later phase, so these workflows rely on explicit state, idempotency, and compensating or recovery operations where applicable.

## Durable provisioning and application delivery

```mermaid
flowchart LR
    Submit["API command<br/>Validate and accept"] --> Intent[("Durable operation<br/>PostgreSQL")]
    Intent --> Claim["Worker claim<br/>Short transaction"]
    Claim --> Effect["External Docker / GitHub effect<br/>No database transaction"]
    Effect --> Result["Persist outcome<br/>Short transaction"]
    Result --> Intent
    Result --> Status["Authorized status query<br/>Dashboard"]
```

- **Resource worker:** creates, reconciles, renews, and removes approved local PostgreSQL resources.
- **Delivery worker:** processes application delivery steps and supports retries and optional GitHub-backed workflows.
- **Recovery:** durable job status, leases, claim tokens, retries, and provider-outcome reconciliation protect against interrupted operations.

**Current behavior:** operation progress is exposed through ordinary API reads. An SSE-based push channel is part of the intended evolution, **not an implemented capability in the reviewed revision**. Worker retry/recovery scheduling remains distinct from frontend progress delivery.

## Runtime and operational boundaries

- **API and dashboard:** core Compose services for local development.
- **Workers:** independent processes, not automatically started by the core Compose stack.
- **PostgreSQL:** source of truth for control-plane resources, identities, and operation state; schema managed explicitly by Alembic.
- **OPA:** policy decisions for identity authorization; project-specific authorization also lives in the platform application.
- **Docker:** implemented local runtime provider; cloud provider support remains future work.
- **Terraform and Ansible:** supporting hosting/bootstrap infrastructure in [`ops/`](../ops/), not proof of an automated production deployment.

## Key source entry points

| Concern | Source |
| --- | --- |
| API assembly and routes | [`backend/src/api/`](../backend/src/api/) |
| Typed dispatch registry | [`backend/src/shared/dispatch.py`](../backend/src/shared/dispatch.py) |
| Platform HTTP transaction boundary | [`backend/src/api/platform/module.py`](../backend/src/api/platform/module.py) |
| Identity module dispatch | [`backend/src/identity/infra/composition/module.py`](../backend/src/identity/infra/composition/module.py) |
| Platform per-operation DI | [`backend/src/devops_platform/infra/composition/providers_action.py`](../backend/src/devops_platform/infra/composition/providers_action.py) |
| Resource worker | [`backend/src/devops_platform/infra/workers/resource_worker.py`](../backend/src/devops_platform/infra/workers/resource_worker.py) |
| Application delivery worker | [`backend/src/devops_platform/infra/workers/application_host.py`](../backend/src/devops_platform/infra/workers/application_host.py) |

*Diagrams document the architecture visible in the current repository; they do not constitute integration or production-readiness certification.*
