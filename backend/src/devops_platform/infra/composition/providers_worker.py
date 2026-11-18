"""Bind application delivery worker hosts at the process boundary."""

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from devops_platform.application.interfaces.software_delivery import ResourceProvisioner
from devops_platform.infra.persistence.repositories.worker_queue import PostgresResourceEffectGuard
from devops_platform.infra.providers.docker_application import DockerApplicationAdapter
from devops_platform.infra.providers.github import GitHubRepositoryAdapter
from devops_platform.infra.security.approval import StaticApprovedImageCatalog
from devops_platform.infra.templates.catalog import FilesystemTemplateCatalog
from devops_platform.infra.workers.application_host import ApplicationDeliveryHost


class ApplicationWorkerProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def delivery_host(
        self,
        engine: AsyncEngine,
        sessions: async_sessionmaker[AsyncSession],
        templates: FilesystemTemplateCatalog,
        images: StaticApprovedImageCatalog,
        repository_provisioner: GitHubRepositoryAdapter | None,
        resources: ResourceProvisioner,
        deployer: DockerApplicationAdapter | None,
    ) -> ApplicationDeliveryHost:
        return ApplicationDeliveryHost(
            sessions=sessions,
            templates=templates,
            images=images,
            repositories=repository_provisioner,
            resources=resources,
            deployer=deployer,
            effect_guard=PostgresResourceEffectGuard(engine),
        )
