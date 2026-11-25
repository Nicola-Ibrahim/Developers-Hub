"""Policy decisions must be enforced before Identity mutations are dispatched."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider
from fastapi.testclient import TestClient

from api.app import create_app
from api.identity.authentication import routes as login_routes
from api.identity.authentication.login_rate_limit import LoginRequestRateLimiter
from api.settings.config import BrowserCookiePolicy
from identity.application.api_tokens.personal_token_messages import CreatePersonalTokenCommand
from identity.application.authentication.authenticate_session.query import AuthenticateSessionQuery
from identity.application.authentication.login.command import LoginCommand
from identity.application.authentication.login.result import LoginResult
from identity.application.authentication.logout.command import LogoutCommand
from identity.application.authorization.models import AuthorizationDecision
from identity.application.interfaces.authorization import (
    AuthorizationDecisionPort,
    AuthorizationUnavailable,
)
from identity.application.interfaces.dispatch import IdentityModule
from identity.application.interfaces.session_tokens import SessionTokenVerifier
from identity.application.interfaces.security import TokenHasher
from identity.domain.records import PersonalApiToken, SessionPrincipal
from identity.infra.security.jwt import JwtSessionTokens

USER, PROJECT, SESSION = uuid4(), uuid4(), uuid4()


class Identity:
    def __init__(self):
        self.commands = []
        self.queries = []

    async def query(self, query):
        self.queries.append(query)
        assert isinstance(query, AuthenticateSessionQuery)
        return SessionPrincipal(
            USER,
            "alice",
            SESSION,
            query.project_id or PROJECT,
            "project",
            "admin",
            (),
            (),
            "csrf",
        )

    async def execute(self, command):
        self.commands.append(command)
        if isinstance(command, LogoutCommand):
            return None
        if isinstance(command, CreatePersonalTokenCommand):
            return PersonalApiToken(
                uuid4(),
                command.name,
                PROJECT,
                command.scopes,
                datetime.now(UTC) + timedelta(hours=command.hours),
                None,
            ), "one-time-secret"
        assert isinstance(command, LoginCommand)
        principal = SessionPrincipal(USER, "alice", SESSION, None, None, None, (), (), "csrf")
        return LoginResult(
            "private-session", "csrf", principal, datetime.now(UTC) + timedelta(hours=8)
        )

    async def execute_with_precondition(self, command, precondition):
        principal = SessionPrincipal(
            USER, "alice", SESSION, PROJECT, "project", "admin", (), (), "csrf"
        )

        class Sessions:
            async def authorize_session_operation(self, *_args, **_kwargs):
                return principal

            async def validate_csrf(self, *_args):
                return True

        class Tokens:
            async def lock_personal_token(self, _token_id):
                return None

        await precondition(Sessions(), Tokens())
        return await self.execute(command)


class Policy:
    def __init__(self, unavailable=False, allowed=False):
        self.calls = []
        self.unavailable = unavailable
        self.allowed = allowed

    async def evaluate(self, request):
        self.calls.append(request)
        if self.unavailable:
            raise AuthorizationUnavailable()
        return AuthorizationDecision(self.allowed, "identity-v1")


class FakeSessionTokenVerifier:
    def verify(self, token: str) -> bool:
        return token == "private-session"


class Bindings(Provider):
    def __init__(self, identity, policy, session_token_verifier=None):
        super().__init__()
        self.identity = identity
        self.policy = policy
        self.session_token_verifier = session_token_verifier or FakeSessionTokenVerifier()

    @provide(scope=Scope.REQUEST)
    def module(self) -> IdentityModule:
        return self.identity

    @provide(scope=Scope.REQUEST)
    def authorizer(self) -> AuthorizationDecisionPort:
        return self.policy

    @provide(scope=Scope.APP)
    def cookies(self) -> BrowserCookiePolicy:
        return BrowserCookiePolicy(False)

    @provide(scope=Scope.APP)
    def session_tokens(self) -> SessionTokenVerifier:
        return self.session_token_verifier

    @provide(scope=Scope.APP)
    def token_hasher(self) -> TokenHasher:
        class Hasher:
            def digest(self, token: str) -> str:
                return token

        return Hasher()


CASES = [
    ("GET", "/api/v1/me/tokens", None, "identity.tokens.read"),
    (
        "POST",
        "/api/v1/me/tokens",
        {"name": "deploy", "scopes": ["catalog:read"], "hours": 2},
        "identity.tokens.write",
    ),
    (
        "POST",
        f"/api/v1/me/tokens/{SESSION}/rotate",
        None,
        "identity.tokens.write",
    ),
    (
        "DELETE",
        f"/api/v1/me/tokens/{SESSION}",
        None,
        "identity.tokens.write",
    ),
    ("GET", "/api/v1/me/browser", None, "identity.sessions.read"),
    ("GET", "/api/v1/me/sessions", None, "identity.sessions.read"),
    ("DELETE", f"/api/v1/me/sessions/{SESSION}", None, "identity.sessions.revoke"),
    ("POST", "/api/v1/auth/logout", None, "identity.logout"),
    ("POST", "/api/v1/auth/logout-all", None, "identity.logout_all"),
    ("POST", "/api/v1/auth/project", {"projectId": str(PROJECT)}, "identity.project.select"),
    (
        "POST",
        "/api/v1/me/password",
        {"currentPassword": "old-password", "newPassword": "new-password-value"},
        "identity.password.change",
    ),
    ("GET", f"/api/v1/projects/{PROJECT}/members", None, "identity.members.read"),
    (
        "PUT",
        f"/api/v1/projects/{PROJECT}/members/{USER}",
        {"role": "developer"},
        "identity.members.write",
    ),
    ("DELETE", f"/api/v1/projects/{PROJECT}/members/{USER}", None, "identity.members.write"),
]


@pytest.mark.parametrize("method,path,body,action", CASES)
@pytest.mark.parametrize("unavailable", [False, True])
def test_policy_denial_blocks_every_protected_identity_action(
    method, path, body, action, unavailable
):
    identity, policy = Identity(), Policy(unavailable)
    container = make_async_container(Bindings(identity, policy), FastapiProvider())
    try:
        with TestClient(create_app(container=container)) as client:
            client.cookies.set("devops_session", "private-session")
            response = client.request(
                method,
                path,
                json=body,
                headers={
                    "X-CSRF-Token": "csrf",
                    "Origin": "http://localhost:3000",
                },
            )
        assert response.status_code == (503 if unavailable else 403)
        assert not identity.commands
        assert len(identity.queries) == 1
        assert len(policy.calls) == 1
        assert policy.calls[0].action == action
        assert policy.calls[0].subject_id == USER
        if "/me/tokens" in path:
            assert policy.calls[0].resource_kind == "token"
            assert policy.calls[0].owner_id == USER
        if "/projects/" in path or path == "/api/v1/auth/project":
            assert identity.queries[0].project_id == PROJECT
            assert policy.calls[0].subject_project_id == PROJECT
        assert "private-session" not in response.text
    finally:
        asyncio.run(container.close())


def test_login_is_available_when_policy_service_is_unavailable():
    identity, policy = Identity(), Policy(True)
    container = make_async_container(Bindings(identity, policy), FastapiProvider())
    try:
        with TestClient(create_app(container=container)) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={"userName": "alice", "password": "password"},
                headers={"Origin": "http://localhost:3000"},
            )
        assert response.status_code == 200
        assert len(identity.commands) == 1
        assert not policy.calls
        assert "HttpOnly" in response.headers["set-cookie"]
    finally:
        asyncio.run(container.close())


def test_login_request_limit_uses_direct_peer_and_ignores_forwarded_headers(monkeypatch):
    identity, policy = Identity(), Policy(True)
    container = make_async_container(Bindings(identity, policy), FastapiProvider())
    monkeypatch.setattr(
        login_routes, "login_request_rate_limiter", LoginRequestRateLimiter(max_requests=1)
    )
    try:
        with TestClient(create_app(container=container)) as client:
            payload = {"userName": "alice", "password": "password"}
            first = client.post(
                "/api/v1/auth/login",
                json=payload,
                headers={"X-Forwarded-For": "198.51.100.1", "Origin": "http://localhost:3000"},
            )
            limited = client.post(
                "/api/v1/auth/login",
                json=payload,
                headers={"X-Forwarded-For": "203.0.113.2", "Origin": "http://localhost:3000"},
            )
        assert first.status_code == 200
        assert limited.status_code == 429
        assert limited.json()["code"] == "login_rate_limited"
        assert len(identity.commands) == 1
        assert not policy.calls
    finally:
        asyncio.run(container.close())


def test_allowed_logout_dispatches_after_policy_check():
    identity, policy = Identity(), Policy(allowed=True)
    container = make_async_container(Bindings(identity, policy), FastapiProvider())
    try:
        with TestClient(create_app(container=container)) as client:
            client.cookies.set("devops_session", "private-session")
            response = client.post(
                "/api/v1/auth/logout",
                headers={"X-CSRF-Token": "csrf", "Origin": "http://localhost:3000"},
            )
        assert response.status_code == 204
        assert len(identity.commands) == 1
        assert isinstance(identity.commands[0], LogoutCommand)
        assert len(policy.calls) == 1
    finally:
        asyncio.run(container.close())


def test_personal_token_route_runs_router_policy_preflight_then_dispatches_message():
    identity, policy = Identity(), Policy(allowed=True)
    container = make_async_container(Bindings(identity, policy), FastapiProvider())
    try:
        with TestClient(create_app(container=container)) as client:
            client.cookies.set("devops_session", "private-session")
            response = client.post(
                "/api/v1/me/tokens",
                json={"name": "deploy", "scopes": ["catalog:read"], "hours": 2},
                headers={"X-CSRF-Token": "csrf", "Origin": "http://localhost:3000"},
            )
        assert response.status_code == 200
        assert response.json()["secret"] == "one-time-secret"
        assert len(policy.calls) == 1
        assert policy.calls[0].action == "identity.tokens.write"
        assert policy.calls[0].resource_kind == "token"
        assert policy.calls[0].owner_id == USER
        assert isinstance(identity.commands[-1], CreatePersonalTokenCommand)
    finally:
        asyncio.run(container.close())


@pytest.mark.parametrize("cookie", ["malformed.cookie.value", "a.b.c"])
def test_malformed_browser_cookie_is_rejected_before_identity_or_policy(cookie):
    identity, policy = Identity(), Policy(allowed=True)
    verifier = JwtSessionTokens("test-signing-material-" * 3)
    container = make_async_container(Bindings(identity, policy, verifier), FastapiProvider())
    try:
        with TestClient(create_app(container=container)) as client:
            client.cookies.set("devops_session", cookie)
            response = client.post(
                "/api/v1/auth/logout",
                headers={"X-CSRF-Token": "csrf", "Origin": "http://localhost:3000"},
            )
        assert response.status_code == 401
        assert not identity.commands
        assert not identity.queries
        assert not policy.calls
    finally:
        asyncio.run(container.close())


@pytest.mark.parametrize("unavailable,expected", [(False, 200), (True, 503)])
def test_authorization_readiness_checks_policy_without_login(unavailable, expected):
    identity, policy = Identity(), Policy(unavailable)
    container = make_async_container(Bindings(identity, policy), FastapiProvider())
    try:
        with TestClient(create_app(container=container)) as client:
            response = client.get("/health/authorization")
        assert response.status_code == expected
        assert not identity.queries
        assert len(policy.calls) == 1
    finally:
        asyncio.run(container.close())
