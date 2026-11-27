"""Password change validation and hashing policy."""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime

from identity.application.accounts.change_password.command import ChangePasswordCommand
from identity.application.interfaces.dispatch import ActionPrecondition
from identity.application.interfaces.identity_transactions import IdentityTransaction
from identity.application.interfaces.security import PasswordHasher
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.user_repository import UserRepository
from identity.domain.records import AccountCredentials
from identity.domain.session_errors import SessionAuthenticationRejected


@dataclass(frozen=True)
class PreparedPasswordChange:
    credential_version: int
    encoded_password: str = field(repr=False)


async def verify_password_change(
    passwords: PasswordHasher,
    account: AccountCredentials | None,
    command: ChangePasswordCommand,
) -> PreparedPasswordChange:
    if account is None or not await asyncio.to_thread(
        passwords.verify,
        command.current_password,
        account.password_hash,
    ):
        raise SessionAuthenticationRejected()
    command.validate_new_password()
    return PreparedPasswordChange(
        account.credential_version,
        await asyncio.to_thread(passwords.hash, command.new_password),
    )


class ChangePasswordHandler:
    def __init__(
        self,
        transaction: IdentityTransaction,
        passwords: PasswordHasher,
    ) -> None:
        self.transaction = transaction
        self.passwords = passwords

    async def execute(
        self, command: ChangePasswordCommand, precondition: ActionPrecondition
    ) -> None:
        async def load_account(
            users: UserRepository, _sessions: SessionRepository
        ) -> AccountCredentials | None:
            return await users.find_login_account(command.actor_name)

        account = await self.transaction.run(load_account)
        if account is None or account.user_id != command.actor_id:
            raise SessionAuthenticationRejected()
        prepared = await verify_password_change(self.passwords, account, command)

        async def update_password(users: UserRepository, sessions: SessionRepository) -> None:
            now = datetime.now(UTC)
            current = await precondition(sessions, None)
            if current.user_id != command.actor_id:
                raise SessionAuthenticationRejected()
            if not await users.change_password(
                user_id=command.actor_id,
                expected_version=prepared.credential_version,
                password_hash=prepared.encoded_password,
                now=now,
            ):
                raise SessionAuthenticationRejected()
            await sessions.revoke_user_sessions(command.actor_id, now)

        await self.transaction.run(update_password)
