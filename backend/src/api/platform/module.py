"""HTTP host: authenticate and complete each platform dispatch transaction."""

from dataclasses import is_dataclass, replace
from typing import Any, Literal, TypeVar, cast

from dishka import AsyncContainer, Scope
from fastapi import Request

from api.composition.browser_access import authenticate_browser_operation
from api.composition.platform_access import authenticate_platform_access
from api.core.security.request_identity import RequestIdentity
from api.identity.authentication.credentials import BrowserCredentials, require_browser_mutation
from devops_platform.application.applications.create_application.command import (
    CreateApplication,
)
from devops_platform.application.applications.get_application.query import (
    ReadApplication,
)
from devops_platform.application.applications.list_applications.query import (
    ReadApplications,
)
from devops_platform.application.applications.read_templates.query import ReadTemplates
from devops_platform.application.interfaces.module import DeveloperPlatformModule
from devops_platform.application.project_access.list_project_members.query import ListProjectMembers
from devops_platform.application.project_access.manage_project_membership.command import (
    ManageProjectMembership,
)
from devops_platform.application.projects.list_projects.query import (
    ReadProjects,
)
from devops_platform.application.shared.dto import AccessContext
from devops_platform.application.shared.errors import PlatformRequestError, ledger_unavailable
from devops_platform.application.software_delivery.attach_database.command import AttachDatabase
from devops_platform.application.software_delivery.deploy_application.command import (
    DeployApplication,
)
from devops_platform.application.software_delivery.handle_preview_webhook.command import (
    ProcessGithubPreviewWebhook,
)
from devops_platform.application.software_delivery.read_deployment_history.query import (
    ReadDeploymentHistory,
)
from devops_platform.application.software_delivery.retry_delivery_step.command import (
    RetryDeliveryStep,
)
from devops_platform.authorization import ALL_SCOPES, authorize_platform_action
from devops_platform.infra.composition.module import DeveloperPlatformModuleDispatcher
from identity.domain.interfaces.project_access import IdentityProjectAccess
from shared.dispatch import Command, Query
from shared.infra.persistence.unit_of_work import DatabaseUnavailable, SqlAlchemyUnitOfWork
from shared.infra.settings import Settings

ResultT = TypeVar("ResultT")
MessageT = TypeVar("MessageT", Command[Any], Query[Any])

_DELIVERY_MESSAGES = (
    CreateApplication,
    AttachDatabase,
    DeployApplication,
    RetryDeliveryStep,
    ReadApplications,
    ReadApplication,
    ReadDeploymentHistory,
    ProcessGithubPreviewWebhook,
)
_MUTATING_BROWSER_MESSAGES = (ManageProjectMembership,)
_ACTION_COMPONENT = "platform_action"


class PlatformRequestModule(DeveloperPlatformModule):
    """HTTP boundary that revalidates credentials and authorizes in one transaction."""

    def __init__(
        self, container: AsyncContainer, request: Request, settings: Settings
    ) -> None:
        self._container = container
        self._request = request
        self._settings = settings

    async def execute(self, command: Command[ResultT]) -> ResultT:
        if isinstance(command, ProcessGithubPreviewWebhook):
            return await self._run_unscoped(command, "execute")
        return await self._run_authorized(command, "execute")

    async def query(self, query: Query[ResultT]) -> ResultT:
        if isinstance(query, ReadTemplates):
            authorize_platform_action(query)
            async with self._container(scope=Scope.ACTION) as action_container:
                inner = DeveloperPlatformModuleDispatcher(
                    lambda handler_type: action_container.get(
                        handler_type, component=_ACTION_COMPONENT
                    )
                )
                return cast(ResultT, await inner.query(query))
        return await self._run_authorized(query, "query")

    async def _run_unscoped(
        self, message: MessageT, method: Literal["execute", "query"]
    ) -> ResultT:
        authorize_platform_action(message)
        async with self._container(scope=Scope.ACTION) as action_container:
            unit = await action_container.get(SqlAlchemyUnitOfWork, component=_ACTION_COMPONENT)
            inner = DeveloperPlatformModuleDispatcher(
                lambda handler_type: action_container.get(handler_type, component=_ACTION_COMPONENT)
            )
            try:
                return await unit.run(
                    lambda: self._dispatch(inner, method, message), lambda result: result
                )
            except DatabaseUnavailable as error:
                raise self._unavailable(message) from error

    async def _run_authorized(
        self, message: MessageT, method: Literal["execute", "query"]
    ) -> ResultT:
        if not is_dataclass(message) or not (
            hasattr(message, "access") or isinstance(message, ReadProjects)
        ):
            raise TypeError("Platform message lacks access context")
        token: RequestIdentity = getattr(self._request.state, "request_identity", None)
        if isinstance(token, BrowserCredentials) and token.mutate:
            require_browser_mutation(self._request, self._settings.browser_allowed_origins)
        async with self._container(scope=Scope.ACTION) as action_container:
            unit = await action_container.get(SqlAlchemyUnitOfWork, component=_ACTION_COMPONENT)
            project_access = await action_container.get(
                IdentityProjectAccess, component=_ACTION_COMPONENT
            )
            inner = DeveloperPlatformModuleDispatcher(
                lambda handler_type: action_container.get(handler_type, component=_ACTION_COMPONENT)
            )

            async def authorized() -> ResultT:
                if isinstance(message, ReadProjects) and isinstance(
                    token, BrowserCredentials
                ):
                    principal = await authenticate_browser_operation(
                        unit.session,
                        token.session_token,
                        None,
                        token_pepper=self._settings.token_pepper.get_secret_value(),
                        project_access=project_access,
                    )
                    accesses = tuple(
                        AccessContext(
                            principal.user_id,
                            member.project_id,
                            cast(Literal["developer", "admin"], member.role),
                            frozenset(ALL_SCOPES),
                        )
                        for member in principal.memberships
                    )
                    current = cast(MessageT, replace(message, accesses=accesses))
                else:
                    if isinstance(token, BrowserCredentials) and isinstance(
                        message, (ListProjectMembers, *_MUTATING_BROWSER_MESSAGES)
                    ):
                        project_id = message.project_id
                        principal = await authenticate_browser_operation(
                            unit.session,
                            token.session_token,
                            project_id,
                            token.csrf_token,
                            token.origin,
                            self._settings.browser_allowed_origins,
                            isinstance(message, _MUTATING_BROWSER_MESSAGES),
                            self._settings.token_pepper.get_secret_value(),
                            project_access=project_access,
                        )
                        if principal.project_id is None or principal.role not in {
                            "developer",
                            "admin",
                        }:
                            raise PlatformRequestError(
                                "project_required", "Select an authorized project", 409
                            )
                        access = AccessContext(
                            principal.user_id,
                            principal.project_id,
                            cast(Literal["developer", "admin"], principal.role),
                            frozenset(principal.scopes),
                        )
                    else:
                        access = await authenticate_platform_access(
                            unit.session, token, self._settings, project_access
                        )
                    if isinstance(message, ReadProjects):
                        current = cast(MessageT, replace(message, accesses=(access,)))
                    else:
                        current = cast(MessageT, replace(message, access=access))
                authorize_platform_action(current)
                return await self._dispatch(inner, method, current)

            try:
                return await unit.run(authorized, lambda result: result)
            except DatabaseUnavailable as error:
                raise self._unavailable(message) from error

    @staticmethod
    async def _dispatch(
        inner: DeveloperPlatformModuleDispatcher,
        method: Literal["execute", "query"],
        message: MessageT,
    ) -> ResultT:
        if method == "execute":
            return await inner.execute(cast(Command[ResultT], message))
        return await inner.query(cast(Query[ResultT], message))

    @staticmethod
    def _unavailable(message: object) -> PlatformRequestError:
        if isinstance(message, _DELIVERY_MESSAGES):
            return PlatformRequestError(
                "delivery_unavailable", "Application delivery database is unavailable", 503
            )
        return ledger_unavailable()
