"""Resource worker process; no migrations or host provisioning at startup."""

import argparse
import asyncio
import json
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend import BackendRuntime
from devops_platform.application.workers.resource_operations.handler import (
    ResourceWorkerHandler,
)
from devops_platform.infra.persistence.repositories.worker_queue import (
    PostgresResourceEffectGuard,
    SqlAlchemyProvisioningQueue,
)
from devops_platform.infra.providers.docker_postgres import DockerPostgresProvider
from devops_platform.infra.security.credentials import FernetResourceCredentialCipher
from shared.application.interfaces.readiness import ReadinessProbe
from shared.infra.settings import Settings


async def run_worker(config: Settings, once: bool = False) -> None:
    if (
        not config.local_provider_enabled
        or config.resource_key is None
        or config.installation_id is None
    ):
        raise ValueError(
            "Worker requires an enabled target, stable installation and credential key"
        )
    runtime = BackendRuntime(config, process="worker")
    try:
        await runtime.start()
        if await (await runtime.container.get(ReadinessProbe)).inspect() != "ready":
            raise ValueError("Worker schema is not ready")
        engine = await runtime.container.get(AsyncEngine)
        sessions = await runtime.container.get(async_sessionmaker[AsyncSession])
        queue = SqlAlchemyProvisioningQueue(
            sessions,
            config.installation_id,
            FernetResourceCredentialCipher(
                config.resource_key.get_secret_value(), config.resource_key_id
            ),
            config.resource_key_id,
        )
        provider = DockerPostgresProvider(
            config.docker_url, config.postgres_image, config.advertised_host
        )
        worker = ResourceWorkerHandler(queue, provider, PostgresResourceEffectGuard(engine))
        last_reconcile = 0.0
        while True:
            try:
                loop = asyncio.get_running_loop()
                if loop.time() - last_reconcile >= 30:
                    await queue.reconcile(await provider.discover(config.installation_id))
                    last_reconcile = loop.time()
                worked = await worker.tick()
                if once:
                    return
                if not worked:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception:
                print(
                    json.dumps(
                        {"event": "worker_operation_failed", "at": datetime.now(UTC).isoformat()}
                    ),
                    flush=True,
                )
                if once:
                    raise
                await asyncio.sleep(2)
    finally:
        await runtime.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Durable local resource worker")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(run_worker(Settings(), args.once))  # type: ignore[call-arg]
    except KeyboardInterrupt:
        pass
    except Exception:
        raise SystemExit(
            "Worker failed. Check private configuration and schema readiness."
        ) from None


if __name__ == "__main__":
    main()
