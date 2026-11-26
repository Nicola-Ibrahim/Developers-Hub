"""PostgreSQL integration coverage for self-service identity profile behavior."""

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session
from test_browser_identity_postgres import ORIGIN, PASSWORD, PEPPER, seed_user
from test_foundation_postgres import async_engine_for, mutation_request

from api.composition.identity_preconditions import (
    browser_read_precondition,
    browser_write_precondition,
)
from api.core.errors import APIError
from composition.container import BackendContainer
from identity.application.authentication.login.command import LoginCommand
from identity.application.interfaces.dispatch import IdentityModule
from identity.application.interfaces.security import TokenHasher
from identity.application.profile.profile_query import ProfileQuery, SecurityHistoryQuery
from identity.application.profile.update_profile import UpdateProfileCommand
from identity.infra.persistence.models.activity import IdentityActivityRow
from identity.infra.persistence.models.session import SessionRow
from identity.infra.persistence.models.user import InternalUserRow
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
                hasher = await scope.get(TokenHasher)
                first_login = await identity.execute(LoginCommand(first_user_name, PASSWORD, None))
                second_login = await identity.execute(
                    LoginCommand(second_user_name, PASSWORD, None)
                )

                first_profile = await identity.query_with_precondition(
                    ProfileQuery(first_user_id),
                    browser_read_precondition(
                        mutation_request(first_login.session_token, first_login.csrf_token, ORIGIN),
                        first_user_id,
                        hasher,
                    ),
                )
                second_profile = await identity.query_with_precondition(
                    ProfileQuery(second_user_id),
                    browser_read_precondition(
                        mutation_request(
                            second_login.session_token, second_login.csrf_token, ORIGIN
                        ),
                        second_user_id,
                        hasher,
                    ),
                )
                assert first_profile.user_id == first_user_id
                assert first_profile.user_name == first_user_name
                assert first_profile.display_name is None
                assert second_profile.user_id == second_user_id
                assert second_profile.user_name == second_user_name
                assert second_profile.display_name is None

                changed = await identity.execute_with_precondition(
                    UpdateProfileCommand(first_user_id, "First User Display"),
                    browser_write_precondition(
                        mutation_request(first_login.session_token, first_login.csrf_token, ORIGIN),
                        first_user_id,
                        hasher,
                    ),
                )
                assert changed.display_name == "First User Display"
                second_profile_after_change = await identity.query_with_precondition(
                    ProfileQuery(second_user_id),
                    browser_read_precondition(
                        mutation_request(
                            second_login.session_token, second_login.csrf_token, ORIGIN
                        ),
                        second_user_id,
                        hasher,
                    ),
                )
                assert second_profile_after_change.display_name is None

                first_history = await identity.query_with_precondition(
                    SecurityHistoryQuery(first_user_id),
                    browser_read_precondition(
                        mutation_request(first_login.session_token, first_login.csrf_token, ORIGIN),
                        first_user_id,
                        hasher,
                    ),
                )
                second_history = await identity.query_with_precondition(
                    SecurityHistoryQuery(second_user_id),
                    browser_read_precondition(
                        mutation_request(
                            second_login.session_token, second_login.csrf_token, ORIGIN
                        ),
                        second_user_id,
                        hasher,
                    ),
                )
                assert any(
                    item.action == "profile_updated" and item.outcome == "succeeded"
                    for item in first_history
                )
                assert all(item.action != "profile_updated" for item in second_history)
                assert {item.id for item in first_history}.isdisjoint(
                    item.id for item in second_history
                )

                with pytest.raises(APIError) as rejected:
                    await identity.execute_with_precondition(
                        UpdateProfileCommand(first_user_id, "Must Roll Back"),
                        browser_write_precondition(
                            mutation_request(first_login.session_token, "invalid-csrf", ORIGIN),
                            first_user_id,
                            hasher,
                        ),
                    )
                assert rejected.value.status == 401
                assert rejected.value.code == "authentication_rejected"

                guard = browser_write_precondition(
                    mutation_request(first_login.session_token, first_login.csrf_token, ORIGIN),
                    first_user_id,
                    hasher,
                )
                async with database.begin() as connection:
                    await connection.execute(
                        update(SessionRow)
                        .where(SessionRow.id == first_login.principal.session_id)
                        .values(revoked_at=datetime.now(UTC))
                    )
                with pytest.raises(APIError) as revoked:
                    await identity.execute_with_precondition(
                        UpdateProfileCommand(first_user_id, "Must Stay Revoked"), guard
                    )
                assert revoked.value.status == 401
                assert revoked.value.code == "authentication_rejected"

                fresh_login = await identity.execute(LoginCommand(first_user_name, PASSWORD, None))
                persisted = await identity.query_with_precondition(
                    ProfileQuery(first_user_id),
                    browser_read_precondition(
                        mutation_request(fresh_login.session_token, fresh_login.csrf_token, ORIGIN),
                        first_user_id,
                        hasher,
                    ),
                )
                after_rejection = await identity.query_with_precondition(
                    SecurityHistoryQuery(first_user_id),
                    browser_read_precondition(
                        mutation_request(fresh_login.session_token, fresh_login.csrf_token, ORIGIN),
                        first_user_id,
                        hasher,
                    ),
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
