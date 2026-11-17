# Local development setup

Install Docker Engine/Desktop with Compose v2, Python 3.12/uv for backend checks,
and Node.js 22/npm for frontend development. Start Docker before the local stack.

From the repository root:

```sh
scripts/dev.sh
```

Choose Docker, then start the core services. For direct execution instead:

```sh
scripts/dev.sh up
```

The script initializes missing private component env files and starts the core
local services. Backend and dashboard setup/check commands are documented in
[backend](../backend/README.md) and [frontend](../frontend/README.md).
The [script guide](platform-dev.md) covers nested menus, standalone backend/frontend
launching and the separate `scripts/db.sh` migration menu.

Optional developer-machine bootstrap lives in `ops/local/ansible/`; it installs
local tools and the repository pre-commit hook. Server setup is separate under
`ops/hosting/ansible/` and must never target a developer machine accidentally.
Doppler, AWS and Azure are not prerequisites for the local demonstration.

The core stack contains API, frontend, PostgreSQL, OPA and migrations. Background
workers are not included; provisioning/delivery requests need a separately
configured worker. See [operations](operations.md). Stopping Compose preserves
volumes and component env files; never use global prune or volume deletion for
routine shutdown.
