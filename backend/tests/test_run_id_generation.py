from datetime import datetime

from app.database import Lead, LeadStatus, Run
from app.repositories.base import RunRepository


def test_generate_run_id_uses_max_suffix_not_count(db_session):
    """After gaps/deletes, next ID must be max(suffix)+1, not count+1."""
    year = datetime.utcnow().year
    db_session.add(
        Lead(
            lead_id="LEAD-GAP-TEST",
            tenant_id="company-a",
            company_name="Gap Co",
            industry="Unknown",
            employee_count=1,
            requirement="test",
            budget=0,
            contact_name="Tester",
            contact_role="Rep",
            email="gap@example.com",
            source="Teams",
            status=LeadStatus.PENDING_QUALIFICATION.value,
        )
    )
    db_session.flush()
    # Sparse IDs: only two rows, highest suffix is 10 (count+1 would wrongly yield 3)
    for suffix in (5, 10):
        db_session.add(
            Run(
                run_id=f"RUN-{year}-{suffix:06d}",
                tenant_id="company-a",
                source="teams",
                trigger_type="test",
                lead_id="LEAD-GAP-TEST",
                owner="tester",
                budget_limit=100,
                state="HANDED_OFF",
                correlation_id=f"CORR-GAP-{suffix}",
                inbound_event_id=f"evt-gap-{suffix}",
            )
        )
    db_session.commit()

    # Delete one so row count is not aligned with max suffix
    doomed = db_session.query(Run).filter(Run.run_id == f"RUN-{year}-000005").one()
    db_session.delete(doomed)
    db_session.commit()

    repo = RunRepository(db_session)
    next_id = repo.generate_run_id()
    assert next_id == f"RUN-{year}-000011"
