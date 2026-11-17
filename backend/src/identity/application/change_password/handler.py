"""Password change validation and hashing policy."""

import asyncio
from dataclasses import dataclass, field

from identity.application.shared.ports import PasswordHasher
from identity.domain.browser_credentials import validate_password
from identity.domain.browser_errors import BrowserAuthenticationRejected
from identity.domain.records import AccountCredentials


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
