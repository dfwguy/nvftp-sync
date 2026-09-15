from nvis_integration.models import ImportRequest
from nvis_integration.state import JobStore


def test_job_creation_is_idempotent(tmp_path):
    store = JobStore(tmp_path / "jobs.sqlite3")
    request = ImportRequest("/nvidia-space/shared/team", "build", "nvis-ova/tool")
    first = store.create(request, requester="U1", channel="C1", idempotency_key="trigger")
    second = store.create(request, requester="U1", channel="C1", idempotency_key="trigger")
    assert first.id == second.id
    approved = store.transition(first.id, expected=("planned",), status="approved")
    assert approved.status == "approved"
    events = store.events(first.id)
    assert [event.event_type for event in events] == ["job.created", "job.approved"]
    assert events[0].actor == "U1"
    assert events[1].previous_hash == events[0].event_hash
    assert store.verify_audit_chain() == (True, 2)


def test_audit_chain_detects_tampering(tmp_path):
    store = JobStore(tmp_path / "jobs.sqlite3")
    request = ImportRequest("/nvidia-space/shared/team", "build", "nvis-ova/tool")
    job = store.create(request, requester="U1", channel="C1", idempotency_key="trigger")
    with store._connect() as connection:
        connection.execute(
            "UPDATE audit_events SET details_json = ? WHERE job_id = ?",
            ('{"tampered":true}', job.id),
        )
    assert store.verify_audit_chain() == (False, 1)
