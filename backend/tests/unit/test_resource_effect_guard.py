"""PostgreSQL effect guards detach their lock connection and end lock transactions."""

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from devops_platform.infra.persistence.repositories.worker_queue import (
    PostgresResourceEffectGuard,
)


class Connection:
    def __init__(self, acquired: bool) -> None:
        self.acquired = acquired
        self.events: list[str] = []
        self.detached = False
        self.in_transaction = False

    def detach(self) -> None:
        self.detached = True
        self.events.append("detach")

    async def run_sync(self, operation):
        return operation(self)

    async def scalar(self, statement, _parameters):
        if "pg_try_advisory_lock" in str(statement):
            self.events.append("acquire")
            self.in_transaction = True
            return self.acquired
        raise AssertionError(f"unexpected scalar query: {statement}")

    async def commit(self) -> None:
        self.events.append("commit")
        self.in_transaction = False

    async def execute(self, statement, _parameters):
        assert "pg_advisory_unlock" in str(statement)
        self.events.append("unlock")
        self.in_transaction = True

    async def invalidate(self) -> None:
        self.events.append("invalidate")


class Engine:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def connect(self):
        @asynccontextmanager
        async def one_off_connection():
            try:
                yield self.connection
            finally:
                assert not self.connection.in_transaction
                self.connection.events.append("close")

        return one_off_connection()


@pytest.mark.parametrize("acquired", [True, False])
def test_effect_guard_detaches_connection_and_has_no_effect_window_transaction(acquired):
    connection = Connection(acquired)
    guard = PostgresResourceEffectGuard(Engine(connection))

    async def exercise() -> None:
        async with guard(uuid4()) as locked:
            assert locked is acquired
            assert connection.detached
            assert not connection.in_transaction
            assert connection.events == ["detach", "acquire", "commit"]
            connection.events.append("external_effect")

    asyncio.run(exercise())

    expected = ["detach", "acquire", "commit", "external_effect"]
    if acquired:
        expected.extend(("unlock", "commit"))
    expected.append("close")
    assert connection.events == expected
