"""PostgreSQL integration coverage for self-service identity profile behavior."""

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session
from test_browser_identity_postgres import ORIGIN, PASSWORD, PEPPER, seed_user
from test_foundation_postgres import async_engine_for, dispatch_browser

from backend import BackendContainer
from identity.application.authentication.login.command import LoginCommand
from identity.application.interfaces.dispatch import IdentityModule
from identity.application.profile.read_profile.query import ProfileQuery
from identity.application.profile.security_history.query import SecurityHistoryQuery
from identity.application.profile.update_profile.command import UpdateProfileCommand
from identity.domain.session_errors import SessionAuthenticationRejected
from identity.infra.persistence.models.activity import IdentityActivityRow
from identity.infra.persistence.models.session import SessionRow
from identity.infra.persistence.models.user import InternalUserRow
from shared.authorization.credentials import RequestCredentials, SessionCredentials
from shared.infra.settings import Settings

pytestmark = pytest.mark.postgres


def test_profile_and_security_history_are_user_owned_and_csrf_failure_rolls_back(
    postgres_engine,
):
    first_user_id, _first_project_id, first_user_name = seed_user(postgres_engine)
    second_user_id, _second_project_id, second_user_name = seed_user(postgres_engine)
    database = async_engine_for(postgres_engine)
    config = Settings(
        database_url="postgresql+psycopg://localhost/devops_hub_test",
        token_pepper=PEPPER,
        browser_allowed_origins=(ORIGIN,),
        cookie_secure=False,
    )

    async def exercise() -> None:
        container = BackendContainer(config, engine=database).combined()
        try:
            async with container() as scope:
                identity = await scope.get(IdentityModule)
                credentials = await scope.get(RequestCredentials)
                first_login = await identity.execute(
                    LoginCommand(user_name=first_user_name, password=PASSWORD, project_id=None)
                )
                second_login = await identity.execute(
                    LoginCommand(user_name=second_user_name, password=PASSWORD, project_id=None)
                )

                first_profile = await dispatch_browser(
                    identity.query,
                    credentials,
                    SessionCredentials(first_login.session_token),
                    ProfileQuery(actor_id=first_user_id),
                )
                second_profile = await dispatch_browser(
                    identity.query,
                    credentials,
                    SessionCredentials(second_login.session_token),
                    ProfileQuery(actor_id=second_user_id),
                )
                assert first_profile.user_id == first_user_id
                assert first_profile.user_name == first_user_name
                assert first_profile.display_name is None
                assert second_profile.user_id == second_user_id
                assert second_profile.user_name == second_user_name
                assert second_profile.display_name is None

                changed = await dispatch_browser(
                    identity.execute,
                    credentials,
                    SessionCredentials(
                        first_login.session_token, csrf_token=first_login.csrf_token
                    ),
                    UpdateProfileCommand(actor_id=first_user_id, display_name="First User Display"),
                )
                assert changed.display_name == "First User Display"
                second_profile_after_change = await dispatch_browser(
                    identity.query,
                    credentials,
                    SessionCredentials(second_login.session_token),
                    ProfileQuery(actor_id=second_user_id),
                )
                assert second_profile_after_change.display_name is None

                first_history = await dispatch_browser(
                    identity.query,
                    credentials,
                    SessionCredentials(first_login.session_token),
                    SecurityHistoryQuery(actor_id=first_user_id),
                )
                second_history = await dispatch_browser(
                    identity.query,
                    credentials,
                    SessionCredentials(second_login.session_token),
                    SecurityHistoryQuery(actor_id=second_user_id),
                )
                assert any(
                    item.action == "profile_updated" and item.outcome == "succeeded"
                    for item in first_history
                )
                assert all(item.action != "profile_updated" for item in second_history)
                assert {item.id for item in first_history}.isdisjoint(
                    item.id for item in second_history
                )

                with pytest.raises(SessionAuthenticationRejected):
                    await dispatch_browser(
                        identity.execute,
                        credentials,
                        SessionCredentials(first_login.session_token, csrf_token="invalid-csrf"),
                        UpdateProfileCommand(actor_id=first_user_id, display_name="Must Roll Back"),
                    )

                session = SessionCredentials(
                    first_login.session_token, csrf_token=first_login.csrf_token
                )
                async with database.begin() as connection:
                    await connection.execute(
                        update(SessionRow)
                        .where(SessionRow.id == first_login.principal.session_id)
                        .values(revoked_at=datetime.now(UTC))
                    )
                with pytest.raises(SessionAuthenticationRejected):
                    await dispatch_browser(
                        identity.execute,
                        credentials,
                        session,
                        UpdateProfileCommand(
                            actor_id=first_user_id, display_name="Must Stay Revoked"
                        ),
                    )

                fresh_login = await identity.execute(
                    LoginCommand(user_name=first_user_name, password=PASSWORD, project_id=None)
                )
                persisted = await dispatch_browser(
                    identity.query,
                    credentials,
                    SessionCredentials(fresh_login.session_token),
                    ProfileQuery(actor_id=first_user_id),
                )
                after_rejection = await dispatch_browser(
                    identity.query,
                    credentials,
                    SessionCredentials(fresh_login.session_token),
                    SecurityHistoryQuery(actor_id=first_user_id),
                )
                assert persisted.display_name == "First User Display"
                assert sum(item.action == "profile_updated" for item in after_rejection) == 1
        finally:
            await container.close()
            await database.dispose()

    asyncio.run(exercise())

    with Session(postgres_engine) as session:
        assert session.get(InternalUserRow, first_user_id).display_name == "First User Display"
        assert session.get(InternalUserRow, second_user_id).display_name is None
        assert (
            session.query(IdentityActivityRow)
            .filter_by(subject_id=first_user_id, action="profile_updated", outcome="succeeded")
            .count()
            == 1
        )
        assert (
            session.query(IdentityActivityRow)
            .filter_by(subject_id=second_user_id, action="profile_updated")
            .count()
            == 0
        )
