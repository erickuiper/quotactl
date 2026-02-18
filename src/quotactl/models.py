"""Data models for quota management."""

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class QuotaSpec:
    """Quota specification for CPU and memory limits/reservations."""

    cpu_limit: Optional[str] = None  # e.g., "2000m"
    memory_limit: Optional[str] = None  # e.g., "4Gi"
    cpu_reservation: Optional[str] = None
    memory_reservation: Optional[str] = None

    def __eq__(self, other: object) -> bool:
        """Compare quota specs for equality."""
        if not isinstance(other, QuotaSpec):
            return False
        return (
            self.cpu_limit == other.cpu_limit
            and self.memory_limit == other.memory_limit
            and self.cpu_reservation == other.cpu_reservation
            and self.memory_reservation == other.memory_reservation
        )

    def is_empty(self) -> bool:
        """Check if quota spec has no values set."""
        return not any(
            [
                self.cpu_limit,
                self.memory_limit,
                self.cpu_reservation,
                self.memory_reservation,
            ]
        )

    def to_rancher_dict(self) -> Dict:
        """Convert to Rancher API format."""
        result: Dict = {}
        limit: Dict = {}
        reservation: Dict = {}

        if self.cpu_limit:
            limit["cpu"] = self.cpu_limit
        if self.memory_limit:
            limit["memory"] = self.memory_limit
        if self.cpu_reservation:
            reservation["cpu"] = self.cpu_reservation
        if self.memory_reservation:
            reservation["memory"] = self.memory_reservation

        if limit:
            result["limit"] = limit
        if reservation:
            result["reservation"] = reservation

        if result:
            return {"resourceQuota": result}
        return {}

    @classmethod
    def from_rancher_dict(cls, data: Dict) -> "QuotaSpec":
        """Create QuotaSpec from Rancher API response.

        Accepts both our format (limit.cpu, reservation.cpu) and Rancher's
        (limit.limitsCpu, limit.requestsCpu, limit.limitsMemory, limit.requestsMemory).
        Also checks data.spec.resourceQuota if present (management API style).
        """
        resource_quota = (
            data.get("resourceQuota")
            or data.get("spec", {}).get("resourceQuota")
            or {}
        )
        limit = resource_quota.get("limit", {})
        reservation = resource_quota.get("reservation", {})

        cpu_limit = limit.get("cpu") or limit.get("limitsCpu")
        memory_limit = limit.get("memory") or limit.get("limitsMemory")
        cpu_reservation = (
            reservation.get("cpu") or limit.get("requestsCpu")
        )
        memory_reservation = (
            reservation.get("memory") or limit.get("requestsMemory")
        )

        return cls(
            cpu_limit=cpu_limit,
            memory_limit=memory_limit,
            cpu_reservation=cpu_reservation,
            memory_reservation=memory_reservation,
        )


@dataclass
class Project:
    """Rancher project representation."""

    id: str
    name: str
    cluster_id: str
    quota: QuotaSpec = field(default_factory=QuotaSpec)

    @classmethod
    def from_rancher_dict(cls, data: Dict) -> "Project":
        """Create Project from Rancher API response."""
        # Prefer displayName (e.g. testing123) over name (e.g. p-65xfh)
        name = (
            data.get("spec", {}).get("displayName")
            or data.get("name")
            or data.get("id", "")
        )
        return cls(
            id=data["id"],
            name=name,
            cluster_id=data.get("clusterId") or data.get("spec", {}).get("clusterName", ""),
            quota=QuotaSpec.from_rancher_dict(data),
        )


@dataclass
class Namespace:
    """Rancher namespace representation."""

    id: str
    name: str
    project_id: str
    quota: QuotaSpec = field(default_factory=QuotaSpec)

    @classmethod
    def from_rancher_dict(cls, data: Dict) -> "Namespace":
        """Create Namespace from Rancher API response."""
        return cls(
            id=data["id"],
            name=data["name"],
            project_id=data.get("projectId", ""),
            quota=QuotaSpec.from_rancher_dict(data),
        )


@dataclass
class QuotaDiff:
    """Difference between current and desired quota."""

    cpu_limit_changed: bool = False
    memory_limit_changed: bool = False
    cpu_reservation_changed: bool = False
    memory_reservation_changed: bool = False

    cpu_limit_old: Optional[str] = None
    cpu_limit_new: Optional[str] = None
    memory_limit_old: Optional[str] = None
    memory_limit_new: Optional[str] = None
    cpu_reservation_old: Optional[str] = None
    cpu_reservation_new: Optional[str] = None
    memory_reservation_old: Optional[str] = None
    memory_reservation_new: Optional[str] = None

    def has_changes(self) -> bool:
        """Check if diff has any changes."""
        return any(
            [
                self.cpu_limit_changed,
                self.memory_limit_changed,
                self.cpu_reservation_changed,
                self.memory_reservation_changed,
            ]
        )

    @classmethod
    def compute(cls, current: QuotaSpec, desired: QuotaSpec) -> "QuotaDiff":
        """Compute diff between current and desired quota."""
        diff = cls()

        if current.cpu_limit != desired.cpu_limit:
            diff.cpu_limit_changed = True
            diff.cpu_limit_old = current.cpu_limit
            diff.cpu_limit_new = desired.cpu_limit

        if current.memory_limit != desired.memory_limit:
            diff.memory_limit_changed = True
            diff.memory_limit_old = current.memory_limit
            diff.memory_limit_new = desired.memory_limit

        if current.cpu_reservation != desired.cpu_reservation:
            diff.cpu_reservation_changed = True
            diff.cpu_reservation_old = current.cpu_reservation
            diff.cpu_reservation_new = desired.cpu_reservation

        if current.memory_reservation != desired.memory_reservation:
            diff.memory_reservation_changed = True
            diff.memory_reservation_old = current.memory_reservation
            diff.memory_reservation_new = desired.memory_reservation

        return diff


@dataclass
class PlanItem:
    """Execution plan item for quota enforcement."""

    resource_type: str  # "project" or "namespace"
    resource_id: str
    resource_name: str
    cluster_id: str
    project_id: Optional[str] = None  # For namespaces
    current: QuotaSpec = field(default_factory=QuotaSpec)
    desired: QuotaSpec = field(default_factory=QuotaSpec)
    diff: QuotaDiff = field(default_factory=QuotaDiff)


@dataclass
class ExecutionResult:
    """Result of quota enforcement execution."""

    success: bool
    plan_item: PlanItem
    error: Optional[str] = None

