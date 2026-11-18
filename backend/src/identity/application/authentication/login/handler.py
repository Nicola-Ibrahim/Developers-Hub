"""Application orchestration for browser password login."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta

from identity.application.authentication.login.command import LoginCommand
from identity.application.authentication.login.result import LoginResult
from identity.application.interfaces.browser_tokens import BrowserSessionTokenIssuer
from identity.application.interfaces.browser_transactions import BrowserTransaction
from identity.application.interfaces.login import LoginCredentialVerifier
from identity.application.interfaces.security import TokenGenerator
from identity.application.shared.session_security import require_browser_origin
from identity.domain.aggregates.user import User
from identity.domain.browser_errors import BrowserAuthenticationRejected
from identity.domain.value_objects.credential_version import CredentialVersion
from identity.domain.value_objects.user_name import UserName


class LoginHandler:
    def __init__(
        self,
        transaction: BrowserTransaction,
        credential_verifier: LoginCredentialVerifier,
        tokens: TokenGenerator,
        clock: Callable[[], datetime],
        digest: Callable[[str], str],
        allowed_origins: tuple[str, ...],
        session_token_issuer: BrowserSessionTokenIssuer,
    ) -> None:
        self.transaction = transaction
        self.credential_verifier = credential_verifier
        self.tokens = tokens
        self.clock = clock
        self.digest = digest
        self.allowed_origins = allowed_origins
        self.session_token_issuer = session_token_issuer

    async def execute(self, command: LoginCommand) -> LoginResult:
        require_browser_origin(command.origin, self.allowed_origins)
        name = UserName.parse(command.user_name).value
        account = await self.transaction.run(lambda repo: repo.find_login_account(name))
        password_matches = await self.credential_verifier.verify(
            command.password, account.password_hash if account is not None else None
        )
        identity_account = (
            User(
                id=account.user_id,
                user_name=UserName.parse(account.user_name),
                credential_version=CredentialVersion(account.credential_version),
                active=account.active,
            )
            if account is not None
            else None
        )
        accepted = bool(
            identity_account is not None
            and identity_account.accepts_credentials(password_matches=password_matches)
        )
        now = self.clock()
        token = self.session_token_issuer.issue(
            str(identity_account.id) if identity_account is not None else "invalid-account",
            now,
            now + timedelta(hours=8),
        )
        csrf = self.tokens.generate()
        result = await self.transaction.run(
            lambda repo: repo.complete_login(
                user_name=name,
                username_digest=self.digest(name),
                expected_version=(
                    identity_account.login_fence() if identity_account is not None else None
                ),
                accepted=accepted,
                token_digest=self.digest(token),
                csrf_digest=self.digest(csrf),
                now=now,
            )
        )
        if result is None:
            raise BrowserAuthenticationRejected()
        principal, _, expires = result
        project_id = command.project_id
        if project_id is not None:
            selected = await self.transaction.run(
                lambda repo: repo.select_project(
                    token_digest=self.digest(token), project_id=project_id, now=self.clock()
                )
            )
            if selected is None:
                await self.transaction.run(
                    lambda repo: repo.logout(self.digest(token), self.clock())
                )
                raise BrowserAuthenticationRejected()
            principal = selected
        return LoginResult(token, csrf, replace(principal, csrf_token=csrf), expires)
