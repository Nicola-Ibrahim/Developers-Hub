"""Application orchestration for password login."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from identity.application.authentication.login.command import LoginCommand
from identity.application.authentication.login.result import LoginResult
from identity.application.interfaces.identity_transactions import IdentityTransaction
from identity.application.interfaces.security import PasswordHasher, TokenGenerator, TokenHasher
from identity.application.interfaces.session_tokens import SessionTokenIssuer
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.user_repository import UserRepository
from identity.domain.records import AccountCredentials, SessionPrincipal
from identity.domain.session_errors import SessionAuthenticationRejected
from identity.domain.value_objects.session_expiry import SessionExpiry


class LoginHandler:
    def __init__(
        self,
        transaction: IdentityTransaction,
        passwords: PasswordHasher,
        tokens: TokenGenerator,
        hasher: TokenHasher,
        session_token_issuer: SessionTokenIssuer,
    ) -> None:
        self.transaction = transaction
        self.passwords = passwords
        self.tokens = tokens
        self.hasher = hasher
        self.session_token_issuer = session_token_issuer

    async def execute(self, command: LoginCommand) -> LoginResult:
        name = command.user_name

        async def read_account(
            users: UserRepository, _sessions: SessionRepository
        ) -> AccountCredentials | None:
            return await users.find_login_account(name)

        account = await self.transaction.run(read_account)
        password_matches = await asyncio.to_thread(
            self.passwords.verify,
            command.password,
            account.password_hash if account is not None else None,
        )
        accepted = bool(account is not None and account.active and password_matches)
        replacement_hash = None
        if account is not None and accepted and self.passwords.needs_rehash(account.password_hash):
            replacement_hash = await asyncio.to_thread(self.passwords.hash, command.password)

        async def complete_login(
            users: UserRepository, sessions: SessionRepository
        ) -> tuple[tuple[SessionPrincipal, UUID, datetime], str, str] | None:
            now = datetime.now(UTC)
            login_account = await users.record_login_attempt(
                user_name=name,
                username_digest=self.hasher.digest(name),
                expected_version=account.credential_version if account is not None else None,
                accepted=accepted,
                replacement_password_hash=replacement_hash,
                now=now,
            )
            if login_account is None:
                return None
            return await self._issue_credentials(sessions, *login_account, now)

        result = await self.transaction.run(complete_login)
        if result is None:
            raise SessionAuthenticationRejected()
        (principal, _, expires), token, csrf = result
        project_id = command.project_id
        if project_id is not None:

            async def select_project(
                _users: UserRepository, sessions: SessionRepository
            ) -> SessionPrincipal | None:
                return await sessions.select_project(
                    token_digest=self.hasher.digest(token),
                    project_id=project_id,
                    now=datetime.now(UTC),
                )

            selected = await self.transaction.run(select_project)
            if selected is None:

                async def revoke_login(_users: UserRepository, sessions: SessionRepository) -> None:
                    await sessions.logout(self.hasher.digest(token), datetime.now(UTC))

                await self.transaction.run(revoke_login)
                raise SessionAuthenticationRejected()
            principal = selected
        return LoginResult(token, csrf, replace(principal, csrf_token=csrf), expires)

    async def _issue_credentials(
        self,
        sessions: SessionRepository,
        user_id: UUID,
        user_name: str,
        credential_version: int,
        now: datetime,
    ) -> tuple[tuple[SessionPrincipal, UUID, datetime], str, str]:
        token = self.session_token_issuer.issue(
            str(user_id), now, SessionExpiry.from_login(now).absolute_at
        )
        csrf = self.tokens.generate()
        session = await sessions.create_login_session(
            user_id=user_id,
            user_name=user_name,
            credential_version=credential_version,
            token_digest=self.hasher.digest(token),
            csrf_digest=self.hasher.digest(csrf),
            now=now,
        )
        return session, token, csrf
