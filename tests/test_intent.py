import pytest

from nvis_integration.intent import Operation, parse_intent


def test_parses_import_aliases_and_natural_language():
    keyed = parse_intent(
        "check-in nvftp=/nvidia-space/shared/release artifact=build-1 target=rack-status",
        "nvis-ova",
    )
    natural = parse_intent(
        "<@U123> import build-1 from /nvidia-space/shared/release into rack-status",
        "nvis-ova",
    )
    assert keyed.operation is Operation.IMPORT
    assert natural == keyed
    assert natural.writes_externally


def test_parses_feature_branch_and_fork_alias():
    intent = parse_intent("fork project=rack-status name=feature/audit-view base=main", "nvis-ova")
    assert intent.operation is Operation.BRANCH
    assert intent.project == "nvis-ova/rack-status"
    assert intent.branch == "feature/audit-view"
    assert intent.base == "main"


@pytest.mark.parametrize(
    "text",
    [
        "branch project=other/group name=feature/x",
        "branch project=repo name=../main",
        "branch project=repo name=feature/x;whoami",
        "import nvftp=/ok artifact=a target=repo extra=bad",
        "do whatever you think is best",
        "status job=not-an-id",
    ],
)
def test_rejects_ambiguous_or_unsafe_text(text):
    with pytest.raises(ValueError):
        parse_intent(text, "nvis-ova")


def test_status_help_cancel_and_replay():
    job = "a" * 32
    assert parse_intent("help", "nvis-ova").operation is Operation.HELP
    assert parse_intent("status", "nvis-ova").job_id is None
    assert parse_intent(f"cancel job={job}", "nvis-ova").job_id == job
    assert parse_intent(f"please replay job {job}", "nvis-ova").operation is Operation.REPLAY


def test_legacy_import_keeps_compatibility():
    intent = parse_intent(
        "nvftp=/nvidia-space/shared artifact=build target=repo",
        "nvis-ova",
        legacy_import=True,
    )
    assert intent.operation is Operation.IMPORT
