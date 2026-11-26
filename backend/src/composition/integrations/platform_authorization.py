"""Authorize Platform operations using trusted request credentials and one SQL transaction."""

from dataclasses import is_dataclass, replace
from typing import Literal, TypeVar, cast

from dishka import AsyncContainer, Scope
from sqlalchemy.ext.asyncio import AsyncSession

from composition.integrations.platform_authentication import (
    authenticate_browser_operation,
    authenticate_platform_access,
)
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
from devops_platform.application.project_access.list_project_members.query import ListProjectMembers
from devops_platform.application.project_access.manage_project_membership.command import (
    ManageProjectMembership,
)
from devops_platform.application.projects.list_projects.query import (
    ReadProjects,
)
from devops_platform.application.shared.dto import AccessContext
from devops_platform.application.shared.errors import (
    CatalogForbidden,
    PlatformRequestError,
    ledger_unavailable,
    resource_not_found,
)
from devops_platform.application.software_delivery.attach_database.command import AttachDatabase
from devops_platform.application.software_delivery.deploy_application.command import (
    DeployApplication,
)
from devops_platform.application.software_delivery.handle_preview_webhook.command import (
    ProcessGithubPreviewWebhook,
)
from devops_platform.application.software_delivery.handle_preview_webhook.handler import (
    ProcessGithubPreviewWebhookHandler,
)
from devops_platform.application.software_delivery.read_deployment_history.query import (
    ReadDeploymentHistory,
)
from devops_platform.application.software_delivery.retry_delivery_step.command import (
    RetryDeliveryStep,
)
from devops_platform.application.software_delivery.shared.models import WebhookResult
from devops_platform.authorization import ALL_SCOPES, authorization_facts
from devops_platform.infra.composition.authorization import trusted_ownership_facts
from devops_platform.infra.composition.module import PLATFORM_HANDLER_REGISTRY
from identity.domain.interfaces.project_access import IdentityProjectAccess
from shared.authorization.credentials import RequestCredentials, SessionCredentials
from shared.authorization.dispatch import require_authorized
from shared.authorization.interfaces import AuthorizationDecisionPort
from shared.authorization.models import AuthorizationRequest
from shared.dispatch import Command, Mediator, Query, UnsupportedMessage
from shared.infra.persistence.unit_of_work import DatabaseUnavailable, SqlAlchemyUnitOfWork
from shared.infra.settings import Settings

ResultT = TypeVar("ResultT")

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
_ACTION_COMPONENT = "platform_action"


class DeveloperPlatformModule:
    """Module boundary that revalidates identity and authorizes in one transaction."""

    def __init__(
        self,
        container: AsyncContainer,
        credentials: RequestCredentials,
        settings: Settings,
        authorizer: AuthorizationDecisionPort,
    ) -> None:
        self._container = container
        self._credentials = credentials
        self._settings = settings
        self._authorizer = authorizer

    async def execute(self, command: Command[ResultT]) -> ResultT:
        if type(command) not in PLATFORM_HANDLER_REGISTRY.commands:
            raise UnsupportedMessage("Unsupported command")
        if isinstance(command, ProcessGithubPreviewWebhook):
            return cast(ResultT, await self._run_signed_webhook(command))
        return await self._run_authorized(command)

    async def query(self, query: Query[ResultT]) -> ResultT:
        if type(query) not in PLATFORM_HANDLER_REGISTRY.queries:
            raise UnsupportedMessage("Unsupported query")
        if isinstance(query, ReadTemplates):
            async with self._container(scope=Scope.ACTION) as action_container:
                return cast(ResultT, await self._mediator(action_container).query(query))
        return await self._run_authorized(query)

    async def _run_signed_webhook(self, command: ProcessGithubPreviewWebhook) -> WebhookResult:
        async with self._container(scope=Scope.ACTION) as action_container:
            unit = await action_container.get(SqlAlchemyUnitOfWork, component=_ACTION_COMPONENT)
            handler = cast(
                ProcessGithubPreviewWebhookHandler,
                await self._mediator(action_container).resolve(command),
            )
            verified = handler.verify_signature(command)
            facts = replace(authorization_facts(command), resource_kind="verified_webhook")

            async def authorize_signed() -> WebhookResult:
                await require_authorized(self._authorizer, command, facts, CatalogForbidden())
                return await handler.execute_verified(command, verified)

            try:
                return await unit.run(authorize_signed, lambda result: result)
            except DatabaseUnavailable as error:
                raise self._unavailable(command) from error

    async def _run_authorized(
        self,
        message: Command[ResultT] | Query[ResultT],
    ) -> ResultT:
        if not is_dataclass(message) or not (
            hasattr(message, "access") or isinstance(message, ReadProjects)
        ):
            raise TypeError("Platform message lacks access context")
        token = self._credentials.identity
        async with self._container(scope=Scope.ACTION) as action_container:
            unit = await action_container.get(SqlAlchemyUnitOfWork, component=_ACTION_COMPONENT)
            project_access = await action_container.get(
                IdentityProjectAccess, component=_ACTION_COMPONENT
            )

            mediator = self._mediator(action_container)

            async def authorized() -> ResultT:
                if isinstance(message, ReadProjects) and isinstance(token, SessionCredentials):
                    principal = await authenticate_browser_operation(
                        unit.session,
                        token,
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
                    current = replace(message, accesses=accesses)
                    if not accesses:
                        facts = AuthorizationRequest(
                            subject_id=principal.user_id,
                            action="",
                            resource_kind="projects",
                        )
                        await require_authorized(
                            self._authorizer, current, facts, CatalogForbidden()
                        )
                    else:
                        await self._authorize_projects(current)
                    return cast(ResultT, await mediator.query(current))

                credentials = token
                if isinstance(token, SessionCredentials) and isinstance(
                    message, (ListProjectMembers, ManageProjectMembership)
                ):
                    credentials = replace(
                        token,
                        project_id=message.project_id,
                        mutate=isinstance(message, ManageProjectMembership),
                    )
                access = await authenticate_platform_access(
                    unit.session, credentials, self._settings, project_access
                )
                current = cast(
                    Command[ResultT] | Query[ResultT],
                    replace(message, accesses=(access,))
                    if isinstance(message, ReadProjects)
                    else replace(message, access=access),
                )
                await self._authorize(current, unit.session, access)
                if isinstance(current, Command):
                    return await mediator.execute(current)
                return await mediator.query(current)

            try:
                return await unit.run(authorized, lambda result: result)
            except DatabaseUnavailable as error:
                raise self._unavailable(message) from error

    async def _authorize_projects(self, message: ReadProjects) -> None:
        unique = {access.project_id: access for access in message.accesses}
        for access in unique.values():
            await require_authorized(
                self._authorizer,
                message,
                authorization_facts(message, access, project_id=access.project_id),
                CatalogForbidden(),
            )

    async def _authorize(
        self,
        message: object,
        session: AsyncSession,
        access: AccessContext,
    ) -> None:
        facts = authorization_facts(message, access)
        if (
            facts.project_id is not None
            and facts.subject_project_id is not None
            and facts.project_id != facts.subject_project_id
        ):
            raise resource_not_found()

        facts = await trusted_ownership_facts(session, message, access, facts)

        message_module = type(message).__module__
        delivery = "software_delivery" in message_module or ".applications." in message_module
        ordinary_denial = (
            PlatformRequestError("forbidden", "Application access is not permitted", 403)
            if delivery
            else CatalogForbidden()
        )

        def denied(reason: str | None) -> Exception:
            if reason == "not_found":
                if facts.resource_kind == "applications":
                    return PlatformRequestError(
                        "application_not_found", "Application was not found", 404
                    )
                return resource_not_found()
            if reason == "ownership":
                if facts.resource_kind == "applications":
                    return PlatformRequestError(
                        "application_not_found", "Application was not found", 404
                    )
                return PlatformRequestError("forbidden", "This action is not permitted", 403)
            return ordinary_denial

        await require_authorized(self._authorizer, message, facts, denied)

    @staticmethod
    def _mediator(container: AsyncContainer) -> Mediator:
        return Mediator(
            PLATFORM_HANDLER_REGISTRY,
            lambda handler_type: container.get(handler_type, component=_ACTION_COMPONENT),
        )

    @staticmethod
    def _unavailable(message: object) -> PlatformRequestError:
        if isinstance(message, _DELIVERY_MESSAGES):
            return PlatformRequestError(
                "delivery_unavailable", "Application delivery database is unavailable", 503
            )
        return ledger_unavailable()
