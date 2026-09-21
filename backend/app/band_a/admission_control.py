from sqlalchemy.orm import Session

from app.config import settings
from app.exceptions import ActiveRunExistsError, AuthenticationError, BudgetExceededError, TenantMismatchError
from app.repositories.base import EventRepository, LeadRepository, RunRepository
from app.security import add_runtime_event, validate_role_for_source


class AdmissionControlService:
    def __init__(self, db: Session):
        self.db = db
        self.runs = RunRepository(db)
        self.events = EventRepository(db)

    def process(
        self,
        normalized: dict,
        *,
        token_claims: dict | None,
        correlation_id: str,
    ) -> tuple[str | None, bool]:
        """Returns (existing_run_id or None, is_duplicate). Raises on rejection."""

        meta = {"correlation_id": correlation_id}

        # Check 1 — Authentication
        if not token_claims:
            add_runtime_event(
                self.db,
                stage="ADMISSION",
                component="admission_control",
                action="authenticate",
                status="FAILED",
                message="Missing or invalid token",
                metadata=meta,
            )
            raise AuthenticationError()

        add_runtime_event(
            self.db,
            stage="ADMISSION",
            component="admission_control",
            action="authenticate",
            status="SUCCESS",
            message=f"Authenticated as {token_claims.get('sub')}",
            metadata=meta,
        )

        role = token_claims.get("role", "")
        source = normalized["source"]
        if not validate_role_for_source(role, source):
            add_runtime_event(
                self.db,
                stage="ADMISSION",
                component="admission_control",
                action="authenticate",
                status="FAILED",
                message=f"Role {role} not allowed for source {source}",
                metadata=meta,
            )
            raise AuthenticationError(f"Role {role} not allowed for source {source}")

        # Check 2 — Tenant resolution
        token_tenant = token_claims.get("tenant_id")
        request_tenant = normalized["tenant_id"]
        if token_tenant != request_tenant:
            add_runtime_event(
                self.db,
                stage="ADMISSION",
                component="admission_control",
                action="resolve_tenant",
                status="FAILED",
                message=f"Tenant mismatch: token={token_tenant}, request={request_tenant}",
                metadata=meta,
            )
            raise TenantMismatchError(
                f"Authenticated tenant {token_tenant} does not match request tenant {request_tenant}"
            )

        add_runtime_event(
            self.db,
            stage="ADMISSION",
            component="admission_control",
            action="resolve_tenant",
            status="SUCCESS",
            message=f"Tenant resolved: {request_tenant}",
            metadata=meta,
        )

        # Check 3 — Deduplication
        existing = self.runs.get_by_event_id(normalized["event_id"])
        if existing:
            add_runtime_event(
                self.db,
                run_id=existing.run_id,
                stage="ADMISSION",
                component="admission_control",
                action="duplicate_detected",
                status="SUCCESS",
                message=f"Duplicate event {normalized['event_id']}, returning existing run",
            )
            add_runtime_event(
                self.db,
                run_id=existing.run_id,
                stage="ADMISSION",
                component="admission_control",
                action="deduplicate",
                status="SUCCESS",
                message="Idempotent outcome",
            )
            return existing.run_id, True

        add_runtime_event(
            self.db,
            stage="ADMISSION",
            component="admission_control",
            action="deduplicate",
            status="SUCCESS",
            message="No duplicate detected",
            metadata=meta,
        )

        # Check 4 — Active run guard
        lead_id = normalized["lead_id"]
        active_run = LeadRepository(self.db).get_active_run_for_lead(lead_id)
        if active_run:
            add_runtime_event(
                self.db,
                run_id=active_run.run_id,
                stage="ADMISSION",
                component="admission_control",
                action="active_run_blocked",
                status="FAILED",
                message=f"Lead {lead_id} already has active run {active_run.run_id}",
                metadata=meta,
            )
            add_runtime_event(
                self.db,
                run_id=active_run.run_id,
                stage="ADMISSION",
                component="admission_control",
                action="rejected",
                status="FAILED",
                message="Lead already has an active run — never becomes a run",
                metadata=meta,
            )
            raise ActiveRunExistsError(
                f"Lead {lead_id} already has active run {active_run.run_id}",
                existing_run_id=active_run.run_id,
            )

        add_runtime_event(
            self.db,
            stage="ADMISSION",
            component="admission_control",
            action="active_run_check",
            status="SUCCESS",
            message=f"No active run blocking lead {lead_id}",
            metadata=meta,
        )

        # Check 5 — Admission budget
        active_count = self.runs.count_active_runs(request_tenant)
        quota = settings.tenant_quota(request_tenant)
        if active_count >= quota:
            add_runtime_event(
                self.db,
                stage="ADMISSION",
                component="admission_control",
                action="admit_budget",
                status="FAILED",
                message=f"Active run budget exceeded: {active_count}/{quota}",
                metadata=meta,
            )
            add_runtime_event(
                self.db,
                stage="ADMISSION",
                component="admission_control",
                action="rejected",
                status="FAILED",
                message="Active run budget exceeded",
                metadata=meta,
            )
            raise BudgetExceededError(
                f"Active run budget exceeded for tenant {request_tenant} ({active_count}/{quota})"
            )

        add_runtime_event(
            self.db,
            stage="ADMISSION",
            component="admission_control",
            action="admit_budget",
            status="SUCCESS",
            message=f"Budget OK: {active_count + 1}/{quota}",
            metadata=meta,
        )

        return None, False
