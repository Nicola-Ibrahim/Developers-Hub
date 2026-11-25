"""PostgreSQL transaction, ownership, membership, and rotation coverage."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Session
from test_browser_identity_postgres import ORIGIN, PEPPER, IdentityFixture, seed_user
from test_foundation_postgres import async_engine_for

from composition.integrations.project_access_persistence import (
    api_token_repository_for_session,
    identity_repositories_for_session,
)
from devops_platform.infra.persistence.models.project_access import ProjectMembershipRow, ProjectRow
from identity.application.api_tokens.manage_personal_tokens import PersonalTokenHandler
from identity.application.api_tokens.personal_token_messages import (
    CreatePersonalTokenCommand,
    ListPersonalTokensQuery,
    RotatePersonalTokenCommand,
)
from identity.application.authentication.login.command import LoginCommand
from identity.application.authentication.logout.command import LogoutCommand
from identity.domain.browser_errors import BrowserAuthenticationRejected
from identity.infra.persistence.models.api_token import ApiAccessTokenRow
from identity.infra.persistence.models.user import InternalUserRow
from identity.infra.security.passwords import ScryptPasswordHasher
from identity.infra.security.tokens import PepperedTokenHasher, SecureTokenGenerator
from shared.infra.persistence.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.postgres


def test_personal_tokens_use_one_action_session_and_preserve_scope_project_and_expiry(
    postgres_engine,
):
    user_id, project_a, username = seed_user(postgres_engine)
    project_b, other_user, other_name = uuid4(), uuid4(), f"operator-{uuid4()}"
    with Session(postgres_engine) as session, session.begin():
        session.add(ProjectRow(id=project_b, name=f"project-{project_b}"))
        session.flush()
        session.add(
            InternalUserRow(
                id=other_user,
                name=other_name,
                active=True,
                password_hash=ScryptPasswordHasher().hash("local-safe-test-password"),
            )
        )
        session.flush()
        session.add_all(
            [
                ProjectMembershipRow(user_id=user_id, project_id=project_b, role="developer"),
                ProjectMembershipRow(user_id=other_user, project_id=project_a, role="developer"),
            ]
        )

    database = async_engine_for(postgres_engine)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    fixed_now = [datetime(2026, 11, 1, tzinfo=UTC)]
    identity = IdentityFixture(sessions, lambda: fixed_now[0])
    hasher = PepperedTokenHasher(PEPPER)
    generator = SecureTokenGenerator()

    async def token_action(message):
        session = sessions()
        _users, browser_sessions = identity_repositories_for_session(session)
        token_repository = api_token_repository_for_session(session)
        handler = PersonalTokenHandler(
            token_repository,
            browser_sessions,
            hasher,
            generator,
            lambda: fixed_now[0],
            ("catalog:read", "resources:read"),
            (ORIGIN,),
        )
        assert token_repository._session is browser_sessions._session is session
        unit = SqlAlchemyUnitOfWork(session)
        assert unit.session is session
        return await unit.run(lambda: handler.execute(message), lambda result: result)

    async def exercise():
        try:
            first = await identity.execute(
                LoginCommand(username, "local-safe-test-password", project_a, ORIGIN)
            )
            second = await identity.execute(
                LoginCommand(username, "local-safe-test-password", project_b, ORIGIN)
            )
            outsider = await identity.execute(
                LoginCommand(other_name, "local-safe-test-password", project_a, ORIGIN)
            )

            created_a, _ = await token_action(
                CreatePersonalTokenCommand(
                    first.session_token, first.csrf_token, ORIGIN, "a", ("catalog:read",), 1
                )
            )
            created_b, _ = await token_action(
                CreatePersonalTokenCommand(
                    second.session_token, second.csrf_token, ORIGIN, "b", ("resources:read",), 8
                )
            )
            assert [
                item.token_id
                for item in await token_action(
                    ListPersonalTokensQuery(first.session_token, project_a)
                )
            ] == [created_a.token_id]
            assert [
                item.token_id
                for item in await token_action(
                    ListPersonalTokensQuery(second.session_token, project_b)
                )
            ] == [created_b.token_id]
            assert (
                await token_action(ListPersonalTokensQuery(outsider.session_token, project_a)) == ()
            )

            fixed_now[0] += timedelta(minutes=10)
            rotated, secret = await token_action(
                RotatePersonalTokenCommand(
                    first.session_token, first.csrf_token, ORIGIN, created_a.token_id
                )
            )
            assert secret
            assert rotated.token_id != created_a.token_id
            assert rotated.expires_at == created_a.expires_at
            assert rotated.scopes == created_a.scopes
            with Session(postgres_engine) as session:
                old = session.get(ApiAccessTokenRow, created_a.token_id)
                new = session.get(ApiAccessTokenRow, rotated.token_id)
                assert old is not None and old.revoked_at == fixed_now[0]
                assert new is not None and new.revoked_at is None
                assert new.expires_at == old.expires_at

            still_active, _ = await token_action(
                CreatePersonalTokenCommand(
                    first.session_token, first.csrf_token, ORIGIN, "rollback", ("catalog:read",), 1
                )
            )
            await identity.execute(LogoutCommand(first.session_token, first.csrf_token, ORIGIN))
            with pytest.raises(BrowserAuthenticationRejected):
                await token_action(
                    RotatePersonalTokenCommand(
                        first.session_token, first.csrf_token, ORIGIN, still_active.token_id
                    )
                )
            with Session(postgres_engine) as session:
                preserved = session.get(ApiAccessTokenRow, still_active.token_id)
                assert preserved is not None and preserved.revoked_at is None
        finally:
            await database.dispose()

    asyncio.run(exercise())
