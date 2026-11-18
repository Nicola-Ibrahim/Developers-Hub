"""Resource lifecycle vocabulary."""

from enum import StrEnum


class ResourceStatus(StrEnum):
    PENDING = "pending"
    PROVISIONING = "provisioning"
    READY = "ready"
    FAILED = "failed"
    DELETING = "deleting"
    CLEANUP_FAILED = "cleanup_failed"
    DELETED = "deleted"


class DesiredState(StrEnum):
    RUNNING = "running"
    DELETED = "deleted"


class DeletionReason(StrEnum):
    REQUESTED = "requested"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PR_CLOSED = "pr_closed"
    PROVISION_FAILED = "provision_failed"
