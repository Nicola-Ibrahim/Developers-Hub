"""HTTP identity routes authenticate through the guarded dispatch surface."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider
from fastapi.testclient import TestClient

from api.app import create_app
from api.settings.config import BrowserCookiePolicy
from identity.application.api_tokens.create_personal_token.command import CreatePersonalTokenCommand
from identity.application.authentication.authenticate_session.query import AuthenticateSessionQuery
from identity.application.authentication.login.command import LoginCommand
from identity.application.authentication.login.result import LoginResult
from identity.application.interfaces.dispatch import IdentityModule
from identity.application.interfaces.session_tokens import SessionTokenVerifier
from identity.application.profile.read_profile.query import ProfileQuery
from identity.application.profile.update_profile.command import UpdateProfileCommand
from identity.application.sessions.revoke_all_sessions.command import RevokeAllSessionsCommand
from identity.application.sessions.revoke_session.command import RevokeSessionCommand
from identity.application.sessions.rotate_csrf.command import RotateCsrfCommand
from identity.application.sessions.select_active_project.command import SelectActiveProjectCommand
from identity.domain.records import AccountProfile, PersonalApiToken, SessionPrincipal
from identity.domain.session_errors import SessionAuthenticationRejected
from identity.infra.security.jwt import JwtSessionTokens
from shared.authorization.credentials import RequestCredentials
from shared.authorization.interfaces import AuthorizationDecisionPort, AuthorizationUnavailable
from shared.authorization.models import AuthorizationDecision

USER, PROJECT, SESSION = uuid4(), uuid4(), uuid4()


class Identity:
    def __init__(self):
        self.commands = []
        self.queries = []
        self.normal_calls = []
        self.guarded_calls = []
        self.executed = []
        self.csrf_valid = True
        self.principal = SessionPrincipal(
            USER, "alice", SESSION, PROJECT, "project", "admin", (), (), "csrf"
        )

    async def query(self, query):
        if isinstance(query, AuthenticateSessionQuery):
            self.normal_calls.append(query)
            return self.principal
        self.guarded_calls.append(query)
        self.queries.append(query)
        self.executed.append(query)
        if isinstance(query, ProfileQuery):
            return AccountProfile(USER, "alice", None)
        return ()

    async def execute(self, command):
        if not isinstance(command, LoginCommand):
            self.guarded_calls.append(command)
            if not self.csrf_valid:
                raise SessionAuthenticationRejected()
            self.executed.append(command)
            return self._result(command)
        self.normal_calls.append(command)
        self.commands.append(command)
        return LoginResult(
            "private-session",
            "csrf",
            self.principal,
            datetime.now(UTC) + timedelta(hours=8),
        )

    def _result(self, message):
        if isinstance(message, SelectActiveProjectCommand | RotateCsrfCommand):
            return self.principal
        if isinstance(message, RevokeAllSessionsCommand):
            return 1
        if isinstance(message, CreatePersonalTokenCommand):
            item = PersonalApiToken(
                uuid4(),
                message.name,
                PROJECT,
                message.scopes,
                datetime.now(UTC) + timedelta(hours=message.hours),
                None,
            )
            return item, "one-time-secret"
        if isinstance(message, UpdateProfileCommand):
            return AccountProfile(USER, "alice", message.display_name)
        if isinstance(message, RevokeSessionCommand):
            return True
        return None


class FakeSessionTokenVerifier:
    def verify(self, token: str) -> bool:
        return token == "private-session"


class Bindings(Provider):
    @provide(scope=Scope.REQUEST)
    def credentials(self) -> RequestCredentials:
        return RequestCredentials()

    def __init__(self, identity, session_token_verifier=None, authorizer=None):
        super().__init__()
        self.identity = identity
        self.session_token_verifier = session_token_verifier or FakeSessionTokenVerifier()
        self.authorizer = authorizer

    @provide(scope=Scope.REQUEST)
    def module(self) -> IdentityModule:
        return self.identity

    @provide(scope=Scope.REQUEST)
    def authorization(self) -> AuthorizationDecisionPort:
        if self.authorizer is None:
            raise AssertionError("authorization provider is not used by this request")
        return self.authorizer

    @provide(scope=Scope.APP)
    def cookies(self) -> BrowserCookiePolicy:
        return BrowserCookiePolicy(False)

    @provide(scope=Scope.APP)
    def session_tokens(self) -> SessionTokenVerifier:
        return self.session_token_verifier


def test_protected_http_reads_and_writes_use_guarded_dispatch():
    identity = Identity()
    container = make_async_container(Bindings(identity), FastapiProvider())
    cases = [
        ("GET", "/api/v1/me/profile", None),
        ("GET", "/api/v1/me/security-history", None),
        ("GET", "/api/v1/me/sessions", None),
        ("GET", "/api/v1/me/tokens", None),
        ("GET", "/api/v1/me/browser", None),
        ("POST", "/api/v1/auth/logout", None),
        ("POST", "/api/v1/auth/logout-all", None),
        ("POST", "/api/v1/auth/project", {"projectId": str(PROJECT)}),
        ("PATCH", "/api/v1/me/profile", {"displayName": "Alice"}),
        ("POST", "/api/v1/me/tokens", {"name": "deploy", "scopes": [], "hours": 2}),
        (
            "POST",
            "/api/v1/me/password",
            {"currentPassword": "old-password", "newPassword": "new-password-value"},
        ),
    ]
    try:
        with TestClient(create_app(container=container)) as client:
            client.cookies.set("devops_session", "private-session")
            for method, path, body in cases:
                response = client.request(
                    method,
                    path,
                    json=body,
                    headers={"X-CSRF-Token": "csrf", "Origin": "http://localhost:3000"},
                )
                assert response.status_code < 500, (method, path, response.text)
        assert len(identity.guarded_calls) == len(cases)
        assert len(identity.normal_calls) == len(cases)
        assert all(isinstance(call, AuthenticateSessionQuery) for call in identity.normal_calls)
    finally:
        asyncio.run(container.close())


@pytest.mark.parametrize("cookie", ["malformed.cookie.value", "a.b.c"])
def test_malformed_browser_cookie_is_rejected_before_identity_dispatch(cookie):
    identity = Identity()
    verifier = JwtSessionTokens("test-signing-material-" * 3)
    container = make_async_container(Bindings(identity, verifier), FastapiProvider())
    try:
        with TestClient(create_app(container=container)) as client:
            client.cookies.set("devops_session", cookie)
            response = client.post(
                "/api/v1/auth/logout",
                headers={"X-CSRF-Token": "csrf", "Origin": "http://localhost:3000"},
            )
        assert response.status_code == 401
        assert not identity.guarded_calls
        assert not identity.queries
    finally:
        asyncio.run(container.close())


def test_missing_csrf_uses_fastapi_required_header_validation():
    identity = Identity()
    container = make_async_container(Bindings(identity), FastapiProvider())
    try:
        with TestClient(create_app(container=container)) as client:
            client.cookies.set("devops_session", "private-session")
            response = client.post(
                "/api/v1/auth/logout", headers={"Origin": "http://localhost:3000"}
            )
        assert response.status_code == 422
        assert not identity.guarded_calls
    finally:
        asyncio.run(container.close())


def test_invalid_supplied_csrf_is_rejected_by_transactional_precondition():
    identity = Identity()
    identity.csrf_valid = False
    container = make_async_container(Bindings(identity), FastapiProvider())
    try:
        with TestClient(create_app(container=container)) as client:
            client.cookies.set("devops_session", "private-session")
            response = client.post(
                "/api/v1/auth/logout",
                headers={
                    "X-CSRF-Token": "invalid",
                    "Origin": "http://localhost:3000",
                },
            )
        assert response.status_code == 401
        assert not identity.executed
    finally:
        asyncio.run(container.close())


def test_bad_origin_remains_unauthorized_and_malformed_project_body_is_422():
    identity = Identity()
    container = make_async_container(Bindings(identity), FastapiProvider())
    try:
        with TestClient(create_app(container=container)) as client:
            client.cookies.set("devops_session", "private-session")
            denied = client.post(
                "/api/v1/auth/logout",
                headers={"X-CSRF-Token": "csrf", "Origin": "https://outside.test"},
            )
            malformed = client.post(
                "/api/v1/auth/project",
                json={"projectId": "not-a-uuid"},
                headers={"X-CSRF-Token": "csrf", "Origin": "http://localhost:3000"},
            )
        assert denied.status_code == 401
        assert malformed.status_code == 422
        assert not identity.guarded_calls
    finally:
        asyncio.run(container.close())


def test_login_is_available_without_authorization_provider_and_keeps_cookie_response():
    identity = Identity()
    container = make_async_container(Bindings(identity), FastapiProvider())
    try:
        with TestClient(create_app(container=container)) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={"userName": "alice", "password": "password"},
                headers={"Origin": "http://localhost:3000"},
            )
        assert response.status_code == 200
        assert response.json()["csrfToken"] == "csrf"
        assert "HttpOnly" in response.headers["set-cookie"]
        assert len(identity.commands) == 1
        assert isinstance(identity.commands[0], LoginCommand)
        assert not identity.guarded_calls
    finally:
        asyncio.run(container.close())


@pytest.mark.parametrize("unavailable", [False, True])
def test_authorization_readiness_uses_shared_decision_port(unavailable: bool):
    class Policy:
        def __init__(self):
            self.calls = []

        async def evaluate(self, request):
            self.calls.append(request)
            if unavailable:
                raise AuthorizationUnavailable()
            return AuthorizationDecision(False, "authorization-v1")

    policy = Policy()
    identity = Identity()
    container = make_async_container(Bindings(identity, authorizer=policy), FastapiProvider())
    try:
        with TestClient(create_app(container=container)) as client:
            response = client.get("/health/authorization")
        assert response.status_code == (503 if unavailable else 200)
        assert len(policy.calls) == 1
        assert not identity.guarded_calls
    finally:
        asyncio.run(container.close())
