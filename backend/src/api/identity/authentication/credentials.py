"""Cookie and project-header parsing for internal browser authentication."""

from uuid import UUID

from fastapi import Request

from api.core.errors import APIError
from identity.application.interfaces.session_tokens import SessionTokenVerifier
from shared.authorization.credentials import SessionCredentials

BrowserCredentials = SessionCredentials

SESSION_COOKIE = "devops_session"
PROJECT_HEADER = "X-Project-ID"
CSRF_HEADER = "X-CSRF-Token"


def browser_credentials(request: Request) -> BrowserCredentials:
    """Extract the browser session without accepting ambiguous bearer+cookie identity."""
    cookie = request.cookies.get(SESSION_COOKIE)
    authorization = request.headers.get("authorization")
    if cookie and authorization:
        raise APIError(
            400, "ambiguous_credentials", "Send either a browser session or bearer token"
        )
    raw_project = request.headers.get(PROJECT_HEADER)
    try:
        project_id = UUID(raw_project) if raw_project else None
    except ValueError:
        raise APIError(400, "invalid_project", "Project header must be a UUID") from None
    return BrowserCredentials(
        cookie,
        project_id,
        request.headers.get(CSRF_HEADER),
        request.headers.get("origin"),
        request.method not in {"GET", "HEAD", "OPTIONS"},
    )


def require_cookie_session(credentials: BrowserCredentials) -> str:
    if not credentials.session_token:
        raise APIError(401, "authentication_required", "Browser session is required")
    return credentials.session_token


def require_browser_mutation(request: Request, allowed_origins: tuple[str, ...]) -> None:
    """Reject browser writes at the HTTP boundary before dispatching application work."""
    require_browser_origin(request, allowed_origins)
    if request.headers.get(CSRF_HEADER) is None:
        raise APIError(
            401,
            "authentication_rejected",
            "Credentials or browser session are invalid",
        )


def require_browser_origin(request: Request, allowed_origins: tuple[str, ...]) -> None:
    origin = request.headers.get("origin")
    allowed = {value.rstrip("/") for value in allowed_origins}
    if origin is None or origin.rstrip("/") not in allowed:
        raise APIError(
            401,
            "authentication_rejected",
            "Credentials or browser session are invalid",
        )


def require_valid_browser_session(
    credentials: BrowserCredentials, verifier: SessionTokenVerifier
) -> None:
    if credentials.session_token is not None and not verifier.verify(credentials.session_token):
        raise APIError(401, "authentication_required", "Browser session is invalid")
