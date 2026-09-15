from nvis_integration.operations import OperationStore


def test_branch_operation_is_idempotent_and_audited(tmp_path):
    store = OperationStore(tmp_path / "operations.sqlite3")
    args = {
        "requester": "U1",
        "channel": "C1",
        "project": "nvis-ova/repo",
        "branch": "feature/x",
        "base": "main",
        "idempotency_key": "slack-event-1",
    }
    first = store.create_branch(**args)
    duplicate = store.create_branch(**args)
    assert duplicate.id == first.id
    assert first.status == "planned"
    running = store.transition_branch(first.id, expected=("planned",), status="running", actor="U2")
    completed = store.transition_branch(
        running.id,
        expected=("running",),
        status="succeeded",
        actor="system",
        result_url="https://gitlab.example/repo/-/tree/feature/x",
    )
    assert completed.status == "succeeded"
    assert completed.result_url.endswith("feature/x")
