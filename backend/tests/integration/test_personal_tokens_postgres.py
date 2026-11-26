"""PostgreSQL transaction, ownership, membership, and rotation coverage."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_foundation_postgres import async_engine_for, mutation_request

from api.composition.identity_preconditions import (
    browser_read_precondition,
    browser_write_precondition,
)
from api.core.errors import APIError
from composition.container import BackendContainer
from devops_platform.infra.persistence.models.project_access import ProjectMembershipRow, ProjectRow
from identity.application.api_tokens.personal_token_messages import (
    CreatePersonalTokenCommand,
    ListPersonalTokensQuery,
    RotatePersonalTokenCommand,
)
from identity.application.interfaces.dispatch import IdentityModule
from identity.domain.session_errors import SessionAuthenticationRejected
from identity.infra.persistence.models.api_token import ApiAccessTokenRow
from identity.infra.persistence.models.session import SessionRow
from identity.infra.persistence.models.user import InternalUserRow
from identity.infra.security.opaque_secrets import PepperedTokenHasher
from shared.infra.settings import Settings

pytestmark = pytest.mark.postgres
ORIGIN = "http://localhost:3000"
PEPPER = "browser-test-pepper-" * 3


def test_personal_tokens_use_one_action_session_and_preserve_scope_project_and_expiry(
    postgres_engine,
):
    user_id, other_user = uuid4(), uuid4()
    project_a, project_b = uuid4(), uuid4()
    username, other_name = f"operator-{user_id}", f"operator-{other_user}"
    seeded_at = datetime.now(UTC)
    first_session, first_csrf = "first-session", "first-csrf"
    second_session, second_csrf = "second-session", "second-csrf"
    outsider_session, outsider_csrf = "outsider-session", "outsider-csrf"
    hasher = PepperedTokenHasher(PEPPER)
    with Session(postgres_engine) as session, session.begin():
        session.add_all(
            [
                InternalUserRow(id=user_id, name=username, active=True, credential_version=1),
                InternalUserRow(id=other_user, name=other_name, active=True, credential_version=1),
                ProjectRow(id=project_a, name=f"project-{project_a}"),
                ProjectRow(id=project_b, name=f"project-{project_b}"),
            ]
        )
        session.flush()
        session.add_all(
            [
                ProjectMembershipRow(user_id=user_id, project_id=project_a, role="developer"),
                ProjectMembershipRow(user_id=user_id, project_id=project_b, role="developer"),
                ProjectMembershipRow(user_id=other_user, project_id=project_a, role="developer"),
            ]
        )
        for owner_id, project_id, raw_token, raw_csrf in (
            (user_id, project_a, first_session, first_csrf),
            (user_id, project_b, second_session, second_csrf),
            (other_user, project_a, outsider_session, outsider_csrf),
        ):
            session.add(
                SessionRow(
                    id=uuid4(),
                    user_id=owner_id,
                    token_digest=hasher.digest(raw_token),
                    csrf_digest=hasher.digest(raw_csrf),
                    selected_project_id=project_id,
                    credential_version=1,
                    created_at=seeded_at,
                    last_seen_at=seeded_at,
                    idle_expires_at=seeded_at + timedelta(hours=8),
                    absolute_expires_at=seeded_at + timedelta(days=7),
                    revoked_at=None,
                )
            )

    database = async_engine_for(postgres_engine)
    settings = Settings(
        database_url="postgresql+psycopg://localhost/devops_hub_test",
        token_pepper=PEPPER,
        browser_allowed_origins=(ORIGIN,),
    )

    def first_guard():
        return browser_write_precondition(
            mutation_request(first_session, first_csrf, ORIGIN),
            user_id,
            hasher,
        )

    def second_guard():
        return browser_write_precondition(
            mutation_request(second_session, second_csrf, ORIGIN),
            user_id,
            hasher,
        )

    async def use_module(identity: IdentityModule):
        created_a, _ = await identity.execute_with_precondition(
            CreatePersonalTokenCommand(user_id, project_a, "a", ("catalog:read",), 1),
            first_guard(),
        )
        created_b, _ = await identity.execute_with_precondition(
            CreatePersonalTokenCommand(user_id, project_b, "b", ("resources:read",), 8),
            second_guard(),
        )
        assert [
            item.token_id
            for item in await identity.query_with_precondition(
                ListPersonalTokensQuery(user_id, project_a),
                browser_read_precondition(
                    mutation_request(first_session, first_csrf, ORIGIN), user_id, hasher
                ),
            )
        ] == [created_a.token_id]
        assert [
            item.token_id
            for item in await identity.query_with_precondition(
                ListPersonalTokensQuery(user_id, project_b),
                browser_read_precondition(
                    mutation_request(second_session, second_csrf, ORIGIN), user_id, hasher
                ),
            )
        ] == [created_b.token_id]
        assert (
            await identity.query_with_precondition(
                ListPersonalTokensQuery(other_user, project_a),
                browser_read_precondition(
                    mutation_request(outsider_session, outsider_csrf, ORIGIN), other_user, hasher
                ),
            )
            == ()
        )

        rotated, secret = await identity.execute_with_precondition(
            RotatePersonalTokenCommand(user_id, created_a.token_id),
            first_guard(),
        )
        assert secret
        assert rotated.token_id != created_a.token_id
        assert rotated.expires_at == created_a.expires_at
        assert rotated.scopes == created_a.scopes
        with Session(postgres_engine) as session:
            old = session.get(ApiAccessTokenRow, created_a.token_id)
            new = session.get(ApiAccessTokenRow, rotated.token_id)
            assert old is not None and old.revoked_at is not None
            assert new is not None and new.revoked_at is None
            assert new.expires_at == old.expires_at

        with Session(postgres_engine) as session, session.begin():
            current_session = session.scalar(
                select(SessionRow).where(SessionRow.token_digest == hasher.digest(first_session))
            )
            assert current_session is not None
            current_session.revoked_at = datetime.now(UTC)
            switched_session = session.scalar(
                select(SessionRow).where(SessionRow.token_digest == hasher.digest(second_session))
            )
            assert switched_session is not None
            switched_session.selected_project_id = project_a

        with pytest.raises(APIError) as revoked:
            await identity.execute_with_precondition(
                RotatePersonalTokenCommand(user_id, rotated.token_id),
                first_guard(),
            )
        assert revoked.value.status == 401
        with pytest.raises(SessionAuthenticationRejected):
            await identity.execute_with_precondition(
                CreatePersonalTokenCommand(user_id, project_b, "stale", ("resources:read",), 8),
                second_guard(),
            )
        with Session(postgres_engine) as session:
            preserved = session.get(ApiAccessTokenRow, rotated.token_id)
            assert preserved is not None and preserved.revoked_at is None
        assert await identity.query_with_precondition(
            ListPersonalTokensQuery(user_id, project_b),
            browser_read_precondition(
                mutation_request(second_session, second_csrf, ORIGIN), user_id, hasher
            ),
        ) == (created_b,)

    async def exercise():
        container = BackendContainer(settings, engine=database).combined()
        try:
            async with container() as scope:
                await use_module(await scope.get(IdentityModule))
        finally:
            await container.close()
            await database.dispose()

    asyncio.run(exercise())
