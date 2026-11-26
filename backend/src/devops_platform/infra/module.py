"""Own Platform authorization, action transactions and handler dispatch."""

from dataclasses import is_dataclass, replace
from typing import TypeVar, cast

from dishka import AsyncContainer, Scope
from sqlalchemy.ext.asyncio import AsyncSession

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
from devops_platform.application.interfaces.module import (
    DeveloperPlatformModule as DeveloperPlatformModuleContract,
)
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
from devops_platform.authorization import authorization_facts
from devops_platform.infra.handlers import PLATFORM_HANDLER_REGISTRY
from devops_platform.infra.persistence.authorization import trusted_ownership_facts
from devops_platform.infra.persistence.resource_request_authority import project_roles_for_operation
from shared.authorization.dispatch import require_authorized
from shared.authorization.interfaces import AuthorizationDecisionPort
from shared.authorization.models import AuthorizationRequest
from shared.dispatch import Command, Mediator, Query, UnsupportedMessage
from shared.infra.persistence.unit_of_work import DatabaseUnavailable, SqlAlchemyUnitOfWork

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


class DeveloperPlatformModule(DeveloperPlatformModuleContract):
    """Authorize and dispatch Platform commands and queries."""

    def __init__(
        self,
        container: AsyncContainer,
        authorizer: AuthorizationDecisionPort,
    ) -> None:
        self._container = container
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
        async with self._container(scope=Scope.ACTION) as action_container:
            unit = await action_container.get(SqlAlchemyUnitOfWork, component=_ACTION_COMPONENT)
            mediator = self._mediator(action_container)

            async def authorized() -> ResultT:
                if isinstance(message, ReadProjects):
                    current_projects = await self._authorize_projects(message, unit.session)
                    return cast(ResultT, await mediator.query(current_projects))

                access = getattr(message, "access", None)
                if not isinstance(access, AccessContext):
                    raise TypeError("Platform message lacks authenticated access")
                facts = authorization_facts(message, access)
                if facts.project_id != access.project_id:
                    raise resource_not_found()
                roles = await project_roles_for_operation(
                    unit.session,
                    access.user_id,
                    (access.project_id,),
                    membership_target_id=message.user_id
                    if isinstance(message, ManageProjectMembership)
                    else None,
                )
                role = roles.get(access.project_id)
                if role is None:
                    raise CatalogForbidden()
                current_access = replace(access, role=role)
                current = cast(
                    Command[ResultT] | Query[ResultT], replace(message, access=current_access)
                )
                await self._authorize(
                    current, unit.session, current_access, replace(facts, role=role)
                )
                if isinstance(current, Command):
                    return await mediator.execute(current)
                return await mediator.query(current)

            try:
                return await unit.run(authorized, lambda result: result)
            except DatabaseUnavailable as error:
                raise self._unavailable(message) from error

    async def _authorize_projects(
        self, message: ReadProjects, session: AsyncSession
    ) -> ReadProjects:
        if any(access.user_id != message.user_id for access in message.accesses):
            raise CatalogForbidden()
        requested = {access.project_id: access for access in message.accesses}
        roles = await project_roles_for_operation(session, message.user_id, tuple(requested))
        accesses = tuple(
            replace(access, role=roles[project_id])
            for project_id, access in requested.items()
            if project_id in roles
        )
        current = replace(message, accesses=accesses)
        if not accesses:
            await require_authorized(
                self._authorizer,
                current,
                AuthorizationRequest(
                    subject_id=message.user_id, action="", resource_kind="projects"
                ),
                CatalogForbidden(),
            )
        for access in accesses:
            await require_authorized(
                self._authorizer,
                current,
                authorization_facts(current, access, project_id=access.project_id),
                CatalogForbidden(),
            )
        return current

    async def _authorize(
        self,
        message: object,
        session: AsyncSession,
        access: AccessContext,
        facts: AuthorizationRequest,
    ) -> None:
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
