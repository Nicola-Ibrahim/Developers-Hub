"""Dashboard-facing identity contracts against isolated PostgreSQL schemas."""

import asyncio

import pytest
from dishka import Provider, Scope, provide
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_browser_identity_postgres import ORIGIN, PASSWORD, PEPPER, seed_user
from test_foundation_postgres import async_engine_for, client_for

from api.app import create_app
from backend import BackendContainer
from devops_platform.application.resource_management.catalog.query import ReadCatalog
from identity.application.profile.update_profile import UpdateProfileCommand
from identity.infra.persistence.models.user import InternalUserRow
from shared.authorization.dispatch import operation_id
from shared.authorization.interfaces import AuthorizationDecisionPort, AuthorizationUnavailable
from shared.authorization.models import AuthorizationDecision
from shared.infra.settings import Settings

pytestmark = pytest.mark.postgres


def config():
    return Settings(
        database_url="postgresql+psycopg://localhost/devops_hub_test",
        token_pepper=PEPPER,
        cookie_secure=False,
        browser_allowed_origins=(ORIGIN,),
    )


def login(client, name, project_id, password=PASSWORD):
    response = client.post(
        "/api/v1/auth/login",
        headers={"Origin": ORIGIN},
        json={"userName": name, "password": password, "projectId": str(project_id)},
    )
    assert response.status_code == 200
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "no-store" in response.headers["cache-control"]
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrfToken"]}


def test_session_controls_password_change_and_logout_all(postgres_engine):
    _, project_id, name = seed_user(postgres_engine)
    with (
        client_for(postgres_engine, config()) as current,
        client_for(postgres_engine, config()) as other,
    ):
        headers = login(current, name, project_id)
        login(other, name, project_id)
        sessions = current.get("/api/v1/me/sessions")
        assert sessions.status_code == 200
        assert "no-store" in sessions.headers["cache-control"]
        assert len(sessions.json()) == 2
        assert sum(item["current"] for item in sessions.json()) == 1
        target = next(item["sessionId"] for item in sessions.json() if not item["current"])
        assert (
            current.delete(f"/api/v1/me/sessions/{target}", headers={"Origin": ORIGIN}).status_code
            == 422
        )
        assert (
            current.delete(
                f"/api/v1/me/sessions/{target}",
                headers={**headers, "Origin": "https://foreign.invalid"},
            ).status_code
            == 401
        )
        assert other.get("/api/v1/me/sessions").status_code == 200
        assert current.delete(f"/api/v1/me/sessions/{target}", headers=headers).status_code == 204
        assert other.get("/api/v1/me/sessions").status_code == 401
        login(other, name, project_id)
        response = current.post(
            "/api/v1/me/password",
            headers=headers,
            json={"currentPassword": PASSWORD, "newPassword": "replacement-private-test-password"},
        )
        assert response.status_code == 204
        assert current.get("/api/v1/me/sessions").status_code == 401
        assert other.get("/api/v1/me/sessions").status_code == 401
        assert (
            current.post(
                "/api/v1/auth/login",
                headers={"Origin": ORIGIN},
                json={"userName": name, "password": PASSWORD, "projectId": str(project_id)},
            ).status_code
            == 401
        )
        headers = login(current, name, project_id, "replacement-private-test-password")
        login(other, name, project_id, "replacement-private-test-password")
        assert current.post("/api/v1/auth/logout-all", headers=headers).status_code == 200
        assert other.get("/api/v1/me/sessions").status_code == 401
        assert current.get("/api/v1/me/sessions").status_code == 401


def test_membership_administration_enforces_role_project_and_admin_retention(postgres_engine):
    admin_id, project_a, admin_name = seed_user(postgres_engine)
    member_id, project_b, member_name = seed_user(postgres_engine, role="developer")
    with (
        client_for(postgres_engine, config()) as admin,
        client_for(postgres_engine, config()) as member,
    ):
        headers = login(admin, admin_name, project_a)
        route = f"/api/v1/projects/{project_a}/members"
        assert admin.get(f"/api/v1/projects/{project_b}/members").status_code == 401
        assert (
            admin.put(
                f"{route}/{member_id}", headers=headers, json={"role": "developer"}
            ).status_code
            == 204
        )
        member_headers = login(member, member_name, project_a)
        denied_read = member.get(route)
        assert denied_read.status_code == 403
        assert denied_read.json()["code"] == "forbidden"
        denied_write = member.put(
            f"{route}/{member_id}", headers=member_headers, json={"role": "admin"}
        )
        assert denied_write.status_code == 403
        assert denied_write.json()["code"] == "forbidden"
        assert member.get("/api/v1/me/sessions").status_code == 200
        assert admin.delete(f"{route}/{admin_id}", headers=headers).status_code == 422
        assert (
            admin.put(
                f"{route}/{admin_id}", headers=headers, json={"role": "developer"}
            ).status_code
            == 422
        )
        assert (
            admin.put(f"{route}/{member_id}", headers=headers, json={"role": "admin"}).status_code
            == 204
        )
        assert member.get(route).status_code == 200
        members = admin.get(route)
        assert "no-store" in members.headers["cache-control"]
        assert {item["userId"] for item in members.json()} == {str(admin_id), str(member_id)}
        assert admin.delete(f"{route}/{member_id}", headers=headers).status_code == 204
        assert member.get(route).status_code == 401
        assert len(admin.get(route).json()) == 1


@pytest.mark.parametrize("unavailable, expected", [(False, 403), (True, 503)])
def test_shared_policy_denies_identity_and_platform_without_fallback(
    postgres_engine, unavailable, expected
):
    user_id, project_id, name = seed_user(postgres_engine)
    calls = []

    class Decisions:
        async def evaluate(self, request):
            calls.append(request)
            if unavailable:
                raise AuthorizationUnavailable()
            return AuthorizationDecision(False, "authorization-v1")

    class Bindings(Provider):
        @provide(scope=Scope.APP, override=True)
        def decisions(self) -> AuthorizationDecisionPort:
            return Decisions()

    engine = async_engine_for(postgres_engine)
    settings = config()
    container = BackendContainer(settings, engine=engine, overrides=(Bindings(),)).api()
    try:
        with TestClient(create_app(settings, engine=engine, container=container)) as client:
            assert client.get("/api/v1/templates").status_code == 200
            headers = login(client, name, project_id)
            assert calls == []
            profile = client.patch(
                "/api/v1/me/profile", headers=headers, json={"displayName": "Must not persist"}
            )
            catalog = client.get("/api/v1/catalog")
            assert profile.status_code == catalog.status_code == expected
            assert [request.action for request in calls] == [
                operation_id(UpdateProfileCommand),
                operation_id(ReadCatalog),
            ]
            assert all(request.subject_id == user_id for request in calls)
    finally:
        asyncio.run(container.close())
        asyncio.run(engine.dispose())

    with Session(postgres_engine) as session:
        record = session.get(InternalUserRow, user_id)
        assert record is not None and record.display_name is None
