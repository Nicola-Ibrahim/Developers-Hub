"""Pure domain rules for resource lifecycle and lease policy."""

from devops_platform.domain.aggregates.resource_lifecycle import transition_status
from devops_platform.domain.errors import DomainError, LeaseViolation, TransitionViolation
from devops_platform.domain.value_objects.lease import LeasePolicy
from devops_platform.domain.value_objects.statuses import (
    DeletionReason,
    DesiredState,
    ResourceStatus,
)

__all__ = [
    "DeletionReason",
    "DesiredState",
    "DomainError",
    "LeasePolicy",
    "LeaseViolation",
    "ResourceStatus",
    "TransitionViolation",
    "transition_status",
]
