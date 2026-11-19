import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from starlette.requests import Request

from api.core.errors import APIError
from api.identity.authentication.credentials import (
    BrowserCredentials,
    browser_credentials,
    require_valid_browser_session,
)
from identity.application.accounts.change_password.handler import (
    PreparedPasswordChange,
    verify_password_change,
)
from identity.application.authentication.login.command import LoginCommand
from identity.application.authentication.login.handler import (
    LoginHandler,
)
from identity.application.shared.principal import principal_for_project
from identity.application.shared.session_security import BrowserMutationAuthorizer
from identity.domain.browser_credentials import validate_password
from identity.domain.browser_errors import BrowserAuthenticationRejected
from identity.domain.errors import IdentityValidationError
from identity.domain.records import AccountCredentials, MembershipDetails
from identity.domain.value_objects.session_expiry import SessionExpiry
from identity.domain.value_objects.user_name import UserName
from identity.infra.security.browser_tokens import JwtBrowserSessionTokens
from identity.infra.security.login_verifier import (
    LoginCredentialVerifier as InfraLoginCredentialVerifier,
)
from identity.infra.security.passwords import ScryptPasswordHasher


def test_browser_mutation_checks_origin_before_locking_and_rejects_invalid_csrf():
    now = datetime.now(UTC)
    calls = []

    class Repository:
        async def authorize_browser_operation(self, token, project, at, *, lock_for_mutation):
            calls.append((token, project, at, lock_for_mutation))
            return object()

        async def validate_csrf(self, token, csrf):
            calls.append((token, csrf))
            return False

    authorizer = BrowserMutationAuthorizer(
        Repository(), lambda: now, lambda secret: f"digest:{secret}", ("https://hub.test",)
    )
    with pytest.raises(BrowserAuthenticationRejected):
        asyncio.run(authorizer.authorize_mutation("session", "csrf", "https://other.test"))
    assert calls == []

    with pytest.raises(BrowserAuthenticationRejected):
        asyncio.run(authorizer.authorize_mutation("session", "csrf", "https://hub.test/"))
    assert calls == [("digest:session", None, now, True), ("digest:session", "digest:csrf")]


def request(headers=(), cookies=b""):
    raw = [(key.lower().encode(), value.encode()) for key, value in headers]
    if cookies:
        raw.append((b"cookie", cookies))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": raw})


def test_username_and_password_policy_is_normalized_and_bounded():
    assert UserName.parse("  Alice.Dev ").value == "alice.dev"
    with pytest.raises(IdentityValidationError):
        UserName.parse("not a valid username")
    validate_password("correct-horse-battery")
    with pytest.raises(IdentityValidationError):
        validate_password("short")


def test_scrypt_hash_verifies_only_matching_password_and_never_embeds_plaintext():
    hasher = ScryptPasswordHasher()
    encoded = hasher.hash("correct-horse-battery")
    assert "correct-horse-battery" not in encoded
    assert hasher.verify("correct-horse-battery", encoded)
    assert not hasher.verify("wrong-password", encoded)


def test_browser_session_expiry_sets_idle_and_absolute_deadlines():
    now = datetime(2026, 11, 1, tzinfo=UTC)
    expiry = SessionExpiry.from_login(now)
    assert expiry.idle_at == now + timedelta(minutes=30)
    assert expiry.absolute_at == now + timedelta(hours=8)


def test_browser_principal_has_only_live_selected_project_authority():
    user_id, session_id, project_id = uuid4(), uuid4(), uuid4()
    member = MembershipDetails(project_id, "service", "developer")
    selected = principal_for_project(
        user_id=user_id,
        user_name="alice",
        session_id=session_id,
        memberships=(member,),
        project_id=project_id,
        csrf_token="csrf",
    )
    projectless = principal_for_project(
        user_id=user_id,
        user_name="alice",
        session_id=session_id,
        memberships=(member,),
        project_id=uuid4(),
        csrf_token="csrf",
    )
    assert selected.project_id == project_id
    assert selected.role == "developer"
    assert selected.scopes
    assert "csrf" not in repr(selected)
    assert projectless.project_id is None
    assert projectless.role is None
    assert projectless.scopes == ()


def test_browser_transport_parses_project_header_and_rejects_cookie_bearer_ambiguity():
    parsed = browser_credentials(request(headers=[("X-Project-ID", str(uuid4()))]))
    assert parsed.session_token is None and parsed.project_id is not None
    with pytest.raises(APIError) as error:
        browser_credentials(
            request(headers=[("Authorization", "Bearer token")], cookies=b"devops_session=session")
        )
    assert error.value.status == 400
    assert error.value.code == "ambiguous_credentials"


@pytest.mark.parametrize("token", ["malformed.cookie.value", "a.b.c"])
def test_browser_cookie_guard_rejects_malformed_jwt(token):
    verifier = JwtBrowserSessionTokens("test-signing-material-" * 3)
    with pytest.raises(APIError) as error:
        require_valid_browser_session(BrowserCredentials(token, None), verifier)
    assert error.value.status == 401


def test_browser_cookie_guard_rejects_expired_jwt():
    verifier = JwtBrowserSessionTokens("test-signing-material-" * 3)
    now = datetime.now(UTC)
    token = verifier.issue("account", now - timedelta(minutes=2), now - timedelta(minutes=1))
    with pytest.raises(APIError) as error:
        require_valid_browser_session(BrowserCredentials(token, None), verifier)
    assert error.value.status == 401


def test_browser_login_verifier_uses_dummy_hash_for_missing_user():
    hasher = ScryptPasswordHasher()
    verifier = InfraLoginCredentialVerifier(hasher)

    assert not asyncio.run(verifier.verify("wrong-password", None))


def test_login_handler_commits_rejected_credentials_before_returning_rejection():
    events = []

    class Repository:
        async def find_login_account(self, name):
            events.append(("find", name))
            return None

        async def record_login_attempt(self, **values):
            events.append(("complete", values["accepted"]))
            return None

        async def select_project(self, **values):
            raise AssertionError("rejected login cannot select a project")

        async def logout(self, *values):
            raise AssertionError("rejected login cannot compensate")

    class Transaction:
        async def run(self, action):
            events.append("transaction-start")
            result = await action(Repository(), Repository())
            events.append("transaction-commit")
            return result

    class Verifier:
        async def verify(self, password, encoded):
            events.append(("verify", encoded))
            return False

    class Tokens:
        def generate(self):
            return "opaque-secret"

    class SessionTokenIssuer:
        def issue(self, subject, issued_at, expires_at):
            return "session-jwt"

    handler = LoginHandler(
        Transaction(),
        Verifier(),
        Tokens(),
        lambda: datetime.now(UTC),
        lambda secret: f"digest:{secret}",
        ("https://hub.test",),
        SessionTokenIssuer(),
    )

    async def execute():
        with pytest.raises(BrowserAuthenticationRejected):
            await handler.execute(LoginCommand(" Alice ", "wrong", None, "https://hub.test"))

    asyncio.run(execute())
    assert events == [
        "transaction-start",
        ("find", "alice"),
        "transaction-commit",
        ("verify", None),
        "transaction-start",
        ("complete", False),
        "transaction-commit",
    ]


def test_password_change_checks_current_password_and_preserves_version_fence():
    hasher = ScryptPasswordHasher()
    account = AccountCredentials(
        uuid4(), "alice", hasher.hash("current-password-value"), 7, True, ()
    )

    async def check() -> None:
        prepared = await verify_password_change(
            hasher, account, "current-password-value", "new-password-value"
        )
        assert isinstance(prepared, PreparedPasswordChange)
        assert prepared.credential_version == 7
        assert hasher.verify("new-password-value", prepared.encoded_password)
        assert "new-password-value" not in repr(prepared)
        with pytest.raises(BrowserAuthenticationRejected):
            await verify_password_change(
                hasher, account, "incorrect-current-password", "another-new-password"
            )

    asyncio.run(check())
