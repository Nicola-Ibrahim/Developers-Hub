"""Password change validation and hashing policy."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from identity.application.accounts.change_password.command import ChangePasswordCommand
from identity.application.authentication.authenticate_session.handler import authenticate_session
from identity.application.interfaces.browser_transactions import BrowserTransaction
from identity.application.interfaces.security import PasswordHasher
from identity.application.shared.session_security import (
    BrowserMutationAuthorizer,
    DigestSecret,
    require_browser_origin,
)
from identity.domain.browser_credentials import validate_password
from identity.domain.browser_errors import BrowserAuthenticationRejected
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.user_repository import UserRepository
from identity.domain.records import AccountCredentials, SessionPrincipal


@dataclass(frozen=True)
class PreparedPasswordChange:
    credential_version: int
    encoded_password: str = field(repr=False)


async def verify_password_change(
    passwords: PasswordHasher,
    account: AccountCredentials | None,
    current_password: str,
    new_password: str,
) -> PreparedPasswordChange:
    if account is None or not await asyncio.to_thread(
        passwords.verify,
        current_password,
        account.password_hash if account is not None else "",
    ):
        raise BrowserAuthenticationRejected()
    validate_password(new_password)
    return PreparedPasswordChange(
        account.credential_version,
        await asyncio.to_thread(passwords.hash, new_password),
    )


class ChangePasswordHandler:
    def __init__(
        self,
        transaction: BrowserTransaction,
        passwords: PasswordHasher,
        clock: Callable[[], datetime],
        digest_secret: DigestSecret,
        allowed_origins: tuple[str, ...],
    ) -> None:
        self.transaction = transaction
        self.passwords = passwords
        self.clock = clock
        self.digest_secret = digest_secret
        self.allowed_origins = allowed_origins

    async def execute(self, command: ChangePasswordCommand) -> None:
        require_browser_origin(command.origin, self.allowed_origins)

        async def load_account(
            users: UserRepository,
            sessions: SessionRepository,
        ) -> tuple[SessionPrincipal, AccountCredentials | None]:
            principal = await authenticate_session(
                sessions, self.clock, self.digest_secret, command.session_token
            )
            return principal, await users.find_login_account(principal.user_name)

        principal, account = await self.transaction.run(load_account)
        prepared = await verify_password_change(
            self.passwords, account, command.current_password, command.new_password
        )

        async def update_password(users: UserRepository, sessions: SessionRepository) -> None:
            now = self.clock()
            await BrowserMutationAuthorizer(
                sessions, self.clock, self.digest_secret, self.allowed_origins
            ).authorize_mutation(command.session_token, command.csrf_token, command.origin)
            if not await users.change_password(
                user_id=principal.user_id,
                expected_version=prepared.credential_version,
                password_hash=prepared.encoded_password,
                now=now,
            ):
                raise BrowserAuthenticationRejected()
            await sessions.revoke_user_sessions(principal.user_id, now)

        await self.transaction.run(update_password)
