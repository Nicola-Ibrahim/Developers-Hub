# Local developer scripts

Use `scripts/dev.sh` or `scripts/db.sh` from any working directory. With no
arguments in a terminal they open interactive menus. `menu` opens the menu
explicitly; no arguments outside a terminal prints help and performs no action.
No Python command framework or package needs to be installed. Bash owns routing
and prompts; standalone Python helpers handle private env files and safe database
URL validation. There is no embedded Python in the shell scripts.
The two public entrypoints share small modules under `scripts/shell/`; the database
module is shared directly so Back and Quit behave consistently when entered from Dev.

The Dev menu groups Docker, native backend/frontend, database and cache-cleanup
actions. Docker has its own start, stop, status and service-log choices.
Menus use boxed headers, aligned choices and coloured prompts/results on supported
terminals. `NO_COLOR`, a dumb terminal or redirected output selects a readable
presentation without ANSI colour codes.
Invalid choices repeat the prompt; `b` goes back one level and `q` exits. Empty
Enter at a choice menu and EOF also exit. At a required-text prompt, Enter asks
again; at a confirmation, Enter means no. Failed actions report their status and
return to the current menu. Long
running servers/log followers run in the foreground; Ctrl+C interrupts the script.
Cleanup previews its fixed cache paths before asking whether to remove them.

| Command | Behavior |
| --- | --- |
| `scripts/dev.sh` | Open the Dev menu in a terminal |
| `scripts/dev.sh menu` | Explicit interactive menu |
| `scripts/dev.sh help` | Commands and valid options; no side effects |
| `scripts/dev.sh up` | Check Docker, preserve/init private env files, build and wait for core readiness |
| `scripts/dev.sh down` | Stop the core stack while preserving volumes |
| `scripts/dev.sh status` | Service status |
| `scripts/dev.sh logs api` | Follow an allowlisted service's logs |
| `scripts/dev.sh clean` | Preview approved cache directories |
| `scripts/dev.sh clean --apply` | Remove only those caches; refuse symlink paths |
| `scripts/dev.sh backend` | Run a separately configured host API on loopback |
| `scripts/dev.sh frontend` | Run the dashboard on loopback against the host API |

## Native processes

Install component dependencies explicitly first using the component README commands.
The launcher does not synchronize packages, download interpreters, migrate schemas
or start dependencies. Backend execution uses offline `uv run` with frozen project
metadata and no dependency sync. It requires a configured loopback PostgreSQL URL,
loopback `PLATFORM_OPA_URL` and token pepper in process environment or supported
private-file configuration. API startup never applies migrations. For browser
sign-in, configure allowed browser origins for the frontend URL you open and
the cookie policy for local HTTP, as described in the backend guide. The launcher
does not rewrite those identity/security settings.

The generated `backend/.env` and `frontend/.env` are for Compose: hostnames such as
`postgres`, `opa` and `api` are not host addresses. PostgreSQL/OPA in the existing
Compose stack are not published to the host. Supply separately reachable local
dependencies for native backend execution; this menu does not expose new ports.
The native frontend launcher sets its process-only `BACKEND_URL` to
`http://127.0.0.1:8000`, overriding the Compose address without rewriting its env file.

## Database menu

This menu manages the platform control-plane schema, not developer-requested
databases. Choose the target explicitly: **Compose** means the existing local
Compose PostgreSQL service; **host** means an explicitly configured loopback
PostgreSQL database. Neither target allows remote URLs. Targets and actions are
shown without displaying connection credentials.

| Command | Behavior |
| --- | --- |
| `scripts/db.sh` or `scripts/db.sh menu` | Choose target and migration action |
| `scripts/db.sh compose status` | Show current revision and available heads |
| `scripts/db.sh compose history` | Show migration history |
| `scripts/db.sh compose heads` | Show available migration heads |
| `scripts/db.sh compose branches` | Inspect revision branch points |
| `scripts/db.sh compose check` | Check for schema/model drift without creating a revision |
| `scripts/db.sh compose sql` | Preview migration SQL without applying it |
| `scripts/db.sh compose upgrade` | Confirm and apply migrations to head |
| `scripts/db.sh host status` | Read migration status using explicit local process configuration |
| `scripts/db.sh host blank-revision --message "describe the change"` | Create an empty migration to edit manually |
| `scripts/db.sh host autogenerate-revision --message "describe the change"` | Generate a migration from schema/model differences |
| `scripts/db.sh host revision --message "describe the change"` | Confirm and create a revision in the repository |
| `scripts/db.sh host revision --message "describe the change" --autogenerate` | Compare local database and registered metadata; review generated code before applying |

The menu offers blank and autogenerated revisions as separate choices. Host
supports the inspection, check, SQL preview and upgrade commands too. Writes require confirmation in a
terminal or explicit `--yes` for unattended execution. No action runs by default.
Revision creation is host-only so files remain in the repository. Compose commands
use an existing backend image through a temporary migration container, with no
dependency startup, image pull/build or credential generation. Start the local
stack explicitly before using Compose database actions.

For host commands, use the backend's documented environment/private-file settings;
dotenv files are not sourced as shell code. The validation helper rejects ambiguous
or unsupported configuration rather than risk a different database target.
Use uppercase configuration names and choose either a direct value or its private
file setting, not both, for the database URL and native backend token pepper.
Compose validation supports the generated component env format and refuses
interpolated database targets or unsupported secret-file overrides. Host URL query
parameters and libpq service/host-address overrides that can redirect a connection
are refused. Fix the configuration and choose the operation again.

There are no clear, reset, stamp or downgrade actions. Removing control-plane
records can lose ownership, lease and cleanup tracking while external resources
still exist; the baseline downgrade drops the schema. Use resource lifecycle actions
to remove resources and a separately reviewed procedure for database recovery.

Daily startup does not install packages, run Ansible or synchronize dependencies.
Developer-machine installation remains an explicit optional operation under
`ops/local/ansible/`. Backend and frontend dependency/check commands live in their
own READMEs. No compatibility aliases for the old tob/poe developer commands remain.

`scripts/helpers/init_env.py` is an ordinary Python file called by Bash; it is
not an installable package. Component env files are private and persistent.
Cleanup never removes env files, `.local`, databases, Docker volumes, `.venv` or
`node_modules`, and never runs a global prune.

Operational backup/restore and host-storage scripts live in
`ops/hosting/scripts/`; the backend image owns `backend/docker-entrypoint.sh`.
Their Python helpers are separate files. Host-storage initialization can format
a reviewed EBS volume and must never run through the local developer entrypoint.

Run safe script checks without starting containers:

```sh
python3 -m unittest discover -s scripts/tests -v
bash -n scripts/dev.sh scripts/db.sh scripts/shell/*.sh ops/hosting/scripts/*.sh
sh -n backend/docker-entrypoint.sh
```

Opt-in packaged-stack acceptance is a backend pytest test, not a developer command:

```sh
cd backend
PLATFORM_RUN_PACKAGED_ACCEPTANCE=1 PLATFORM_TEST_DOCKER_URL=unix:///var/run/docker.sock \
  .venv/bin/pytest -q tests/acceptance/test_packaged_stack.py
```

Its worker exists only in the disposable acceptance model, outside the normal
five-service Compose stack. It requires prebuilt `devops-hub/backend:acceptance` and
`devops-hub/frontend:acceptance` images (or explicit PLATFORM_TEST_API_IMAGE and
PLATFORM_TEST_FRONTEND_IMAGE references), allocates a unique Compose project and
synthetic credentials, uses local ports 8000/3000, and removes only its owned test
resources. It does not read developer env files. Without explicit opt-in it skips.
This command creates disposable resources; it is separate from the safe checks.
