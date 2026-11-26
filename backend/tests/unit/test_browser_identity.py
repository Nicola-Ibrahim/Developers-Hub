import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from starlette.requests import Request

from api.core.errors import APIError
from api.identity.authentication.credentials import (
    BrowserCredentials,
    browser_credentials,
    require_browser_origin,
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
from identity.application.authentication.logout.command import LogoutCommand
from identity.application.shared.principal import principal_for_project
from identity.domain.errors import IdentityValidationError
from identity.domain.password_policy import validate_password
from identity.domain.records import AccountCredentials, MembershipDetails
from identity.domain.session_errors import SessionAuthenticationRejected
from identity.domain.value_objects.session_expiry import SessionExpiry
from identity.domain.value_objects.user_name import UserName
from identity.infra.module import IdentityModule
from identity.infra.security.jwt import JwtSessionTokens
from identity.infra.security.opaque_secrets import PepperedTokenHasher
from identity.infra.security.passwords import Argon2idPasswordHasher
from shared.authorization.credentials import RequestCredentials


def test_browser_mutation_checks_origin_before_locking_and_rejects_invalid_csrf():
    calls = []
    user_id = uuid4()
    hasher = PepperedTokenHasher("test-session-pepper" * 2)
    principal = principal_for_project(
        user_id=user_id,
        user_name="alice",
        session_id=uuid4(),
        memberships=(),
        project_id=None,
        csrf_token="",
    )

    class Repository:
        async def authorize_session_operation(self, token, project, at, *, lock_for_mutation):
            calls.append((token, project, lock_for_mutation))
            return principal

        async def validate_csrf(self, token, csrf):
            calls.append((token, csrf))
            return False

    async def authorize(origin):
        mutation = request(
            headers=(("Origin", origin), ("X-CSRF-Token", "csrf")),
            cookies=b"devops_session=session",
        )
        require_browser_origin(mutation, ("https://hub.test",))

        class Container:
            async def get(self, _dependency):
                return hasher

        module = IdentityModule(Container(), RequestCredentials(browser_credentials(mutation)))
        check = await module._precondition(LogoutCommand("session"))
        return await check(Repository(), None)

    with pytest.raises(APIError) as origin_denied:
        asyncio.run(authorize("https://other.test"))
    assert origin_denied.value.status == 401
    assert calls == []

    with pytest.raises(SessionAuthenticationRejected):
        asyncio.run(authorize("https://hub.test/"))
    assert calls == [
        (hasher.digest("session"), None, True),
        (hasher.digest("session"), hasher.digest("csrf")),
    ]


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


def test_argon2id_hash_verifies_only_matching_password_and_never_embeds_plaintext():
    hasher = Argon2idPasswordHasher()
    encoded = hasher.hash("correct-horse-battery")
    assert "correct-horse-battery" not in encoded
    assert hasher.verify("correct-horse-battery", encoded)
    assert not hasher.verify("wrong-password", encoded)
    assert not hasher.verify("wrong-password", None)
    assert not hasher.needs_rehash(encoded)


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
    verifier = JwtSessionTokens("test-signing-material-" * 3)
    with pytest.raises(APIError) as error:
        require_valid_browser_session(BrowserCredentials(token, None), verifier)
    assert error.value.status == 401


def test_browser_cookie_guard_rejects_expired_jwt():
    verifier = JwtSessionTokens("test-signing-material-" * 3)
    now = datetime.now(UTC)
    token = verifier.issue("account", now - timedelta(minutes=2), now - timedelta(minutes=1))
    with pytest.raises(APIError) as error:
        require_valid_browser_session(BrowserCredentials(token, None), verifier)
    assert error.value.status == 401


def test_password_adapter_keeps_legacy_scrypt_verification_and_requests_rehash():
    hasher = Argon2idPasswordHasher()
    salt = bytes(range(16))
    value = __import__("hashlib").scrypt(
        b"legacy-password", salt=salt, n=1 << 14, r=8, p=1, dklen=32
    )
    legacy = f"scrypt${1 << 14}$8$1${salt.hex()}${value.hex()}"
    assert hasher.verify("legacy-password", legacy)
    assert hasher.needs_rehash(legacy)


def test_login_handler_commits_rejected_credentials_before_returning_rejection():
    events = []

    class Repository:
        async def find_login_account(self, name):
            events.append(("find", name))
            return None

        async def record_login_attempt(self, **values):
            events.append(("complete", values["accepted"], values["replacement_password_hash"]))
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

    class Tokens:
        def generate(self):
            events.append("csrf-generated")
            return "opaque-secret"

    class SessionTokenIssuer:
        def issue(self, subject, issued_at, expires_at):
            events.append("jwt-issued")
            return "session-jwt"

    handler = LoginHandler(
        Transaction(),
        Argon2idPasswordHasher(),
        Tokens(),
        PepperedTokenHasher("synthetic-pepper-for-login-tests" * 2),
        SessionTokenIssuer(),
    )

    async def execute():
        with pytest.raises(SessionAuthenticationRejected):
            await handler.execute(LoginCommand(" Alice ", "wrong", None))

    asyncio.run(execute())
    assert events == [
        "transaction-start",
        ("find", "alice"),
        "transaction-commit",
        "transaction-start",
        ("complete", False, None),
        "transaction-commit",
    ]


def test_password_change_checks_current_password_and_preserves_version_fence():
    hasher = Argon2idPasswordHasher()
    account = AccountCredentials(uuid4(), "alice", hasher.hash("current-password-value"), 7, True)

    async def check() -> None:
        prepared = await verify_password_change(
            hasher, account, "current-password-value", "new-password-value"
        )
        assert isinstance(prepared, PreparedPasswordChange)
        assert prepared.credential_version == 7
        assert hasher.verify("new-password-value", prepared.encoded_password)
        assert "new-password-value" not in repr(prepared)
        with pytest.raises(SessionAuthenticationRejected):
            await verify_password_change(
                hasher, account, "incorrect-current-password", "another-new-password"
            )

    asyncio.run(check())
