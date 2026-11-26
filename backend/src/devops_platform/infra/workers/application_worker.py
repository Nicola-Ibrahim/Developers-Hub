"""Application delivery worker process; provider effects are adapter-gated."""

import argparse
import asyncio

from backend import BackendRuntime
from devops_platform.infra.workers.application_host import (
    ApplicationDeliveryHost,
    run_application_worker,
)
from shared.application.interfaces.readiness import ReadinessProbe
from shared.infra.settings import Settings


async def run(config: Settings, once: bool = False) -> None:
    runtime = BackendRuntime(config, process="worker")
    try:
        await runtime.start()
        if await (await runtime.container.get(ReadinessProbe)).inspect() != "ready":
            raise ValueError("Application delivery schema is not ready")
        async with runtime.container() as scope:
            service = await scope.get(ApplicationDeliveryHost)
            await run_application_worker(service, once=once)
    finally:
        await runtime.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Durable application delivery worker")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(run(Settings(), args.once))  # type: ignore[call-arg]
    except KeyboardInterrupt:
        pass
    except Exception:
        raise SystemExit(
            "Application worker failed. Check private configuration and schema readiness."
        ) from None


if __name__ == "__main__":
    main()
