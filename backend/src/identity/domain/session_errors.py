"""Session authentication failure."""

from identity.domain.errors import AuthenticationRejected


class SessionAuthenticationRejected(AuthenticationRejected):
    code = "authentication_rejected"
    message = "Credentials or browser session are invalid"

    def __init__(self) -> None:
        Exception.__init__(self, self.message)
