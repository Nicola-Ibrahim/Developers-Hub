"""Explicit identity message registration and lazy module dispatch."""

from dishka import AsyncContainer

from identity.application.accounts.change_password.command import ChangePasswordCommand
from identity.application.accounts.change_password.handler import ChangePasswordHandler
from identity.application.api_tokens.authenticate_api_token.handler import (
    AuthenticateApiTokenHandler,
)
from identity.application.api_tokens.authenticate_api_token.query import AuthenticateApiTokenQuery
from identity.application.authentication.authenticate_session.handler import (
    AuthenticateSessionHandler,
)
from identity.application.authentication.authenticate_session.query import AuthenticateSessionQuery
from identity.application.authentication.login.command import LoginCommand
from identity.application.authentication.login.handler import LoginHandler
from identity.application.authentication.logout.command import LogoutCommand
from identity.application.authentication.logout.handler import LogoutHandler
from identity.application.project_access.list_project_members.handler import (
    ListProjectMembersHandler,
)
from identity.application.project_access.list_project_members.query import ListProjectMembersQuery
from identity.application.project_access.manage_project_membership.command import (
    ManageProjectMembershipCommand,
)
from identity.application.project_access.manage_project_membership.handler import (
    ManageProjectMembershipHandler,
)
from identity.application.sessions.list_sessions.handler import ListSessionsHandler
from identity.application.sessions.list_sessions.query import ListSessionsQuery
from identity.application.sessions.revoke_all_sessions.command import RevokeAllSessionsCommand
from identity.application.sessions.revoke_all_sessions.handler import RevokeAllSessionsHandler
from identity.application.sessions.revoke_session.command import RevokeSessionCommand
from identity.application.sessions.revoke_session.handler import RevokeSessionHandler
from identity.application.sessions.rotate_csrf.command import RotateCsrfCommand
from identity.application.sessions.rotate_csrf.handler import RotateCsrfHandler
from identity.application.sessions.select_active_project.command import (
    SelectActiveProjectCommand,
)
from identity.application.sessions.select_active_project.handler import (
    SelectActiveProjectHandler,
)
from shared.dispatch import HandlerRegistry, ModuleDispatcher

IDENTITY_HANDLER_REGISTRY = HandlerRegistry(
    commands=(
        (LoginCommand, LoginHandler),
        (RotateCsrfCommand, RotateCsrfHandler),
        (SelectActiveProjectCommand, SelectActiveProjectHandler),
        (LogoutCommand, LogoutHandler),
        (RevokeAllSessionsCommand, RevokeAllSessionsHandler),
        (RevokeSessionCommand, RevokeSessionHandler),
        (ChangePasswordCommand, ChangePasswordHandler),
        (ManageProjectMembershipCommand, ManageProjectMembershipHandler),
    ),
    queries=(
        (AuthenticateApiTokenQuery, AuthenticateApiTokenHandler),
        (AuthenticateSessionQuery, AuthenticateSessionHandler),
        (ListSessionsQuery, ListSessionsHandler),
        (ListProjectMembersQuery, ListProjectMembersHandler),
    ),
    required_commands=(
        LoginCommand,
        RotateCsrfCommand,
        SelectActiveProjectCommand,
        LogoutCommand,
        RevokeAllSessionsCommand,
        RevokeSessionCommand,
        ChangePasswordCommand,
        ManageProjectMembershipCommand,
    ),
    required_queries=(
        AuthenticateApiTokenQuery,
        AuthenticateSessionQuery,
        ListSessionsQuery,
        ListProjectMembersQuery,
    ),
)


class IdentityModuleDispatcher(ModuleDispatcher):
    def __init__(self, container: AsyncContainer) -> None:
        super().__init__(IDENTITY_HANDLER_REGISTRY, container.get)
