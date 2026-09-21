from app.database import RunState
from app.repositories.base import QueueRepository, RunRepository


def test_run_creation(db_session):
    runs = RunRepository(db_session)
    run = runs.create_run(
        tenant_id="company-a",
        source="zoho",
        trigger_type="zoho_webhook",
        lead_id="LEAD-10001",
        owner="zoho-simulator",
        budget_limit=100,
        correlation_id="CORR-TEST",
        inbound_event_id="evt-1",
    )
    assert run.run_id.startswith("RUN-")
    assert run.state == RunState.ADMITTED.value


def test_queue_enqueue_dequeue(db_session):
    runs = RunRepository(db_session)
    run = runs.create_run(
        tenant_id="company-a",
        source="teams",
        trigger_type="teams_manual",
        lead_id="LEAD-10001",
        owner="user",
        budget_limit=100,
        correlation_id="CORR-Q",
        inbound_event_id="evt-q",
    )
    db_session.commit()

    queue = QueueRepository(db_session)
    msg = queue.enqueue(run_id=run.run_id, tenant_id="company-a", lead_id="LEAD-10001", source="teams")
    assert msg.status == "PENDING"

    dequeued = queue.dequeue_next()
    assert dequeued.message_id == msg.message_id
    assert dequeued.status == "PROCESSING"


def test_active_run_count(db_session):
    runs = RunRepository(db_session)
    count = runs.count_active_runs("company-a")
    assert count >= 0
