class IdentityUnavailable(Exception):
    code = "database_unavailable"
    message = "Database unavailable"

    def __init__(self) -> None:
        super().__init__(self.message)
