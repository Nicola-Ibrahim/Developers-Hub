from devops_platform.application.interfaces.resources import ResourceRepository
from devops_platform.application.resource_management.get_operation.query import ReadOperation
from devops_platform.application.resource_management.read_models import OperationDetails
from devops_platform.application.shared.errors import resource_not_found


class ReadOperationHandler:
    def __init__(self, repository: ResourceRepository) -> None:
        self.repository = repository

    async def execute(self, query: ReadOperation) -> OperationDetails:
        operation = await self.repository.find_operation(
            query.access.project_id, query.operation_id
        )
        if operation is None:
            raise resource_not_found()
        return operation
