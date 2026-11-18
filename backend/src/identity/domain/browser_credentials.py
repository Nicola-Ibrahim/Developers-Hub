"""Password requirements for internal browser accounts."""

from identity.domain.errors import IdentityValidationError


def validate_password(value: str) -> None:
    if len(value) < 12 or len(value) > 1024:
        raise IdentityValidationError("Password must contain between 12 and 1024 characters")
