import pytest

from nvis_integration.config import Routing
from nvis_integration.models import ensure_allowed_source, parse_import_command
from nvis_integration.routing import resolve_target


def test_parse_valid_command():
    request = parse_import_command(
        "nvftp=/nvidia-space/shared/team artifact=build_2026-01-01_abcd123 "
        "target=nvis-ova/tool",
        "nvis-ova",
    )
    assert request.target == "nvis-ova/tool"


def test_auto_target_uses_reviewed_exact_route():
    request = parse_import_command(
        "nvftp=/nvidia-space/shared/NscaleTX-16K/RackStatus_PythonCM artifact=release",
        "nvis-ova",
    )
    resolved = resolve_target(
        request,
        Routing(
            exact_sources={
                "/nvidia-space/shared/NscaleTX-16K/RackStatus_PythonCM":
                    "nvis-ova/rack-status-pythoncm"
            }
        ),
    )
    assert resolved.target == "nvis-ova/rack-status-pythoncm"


def test_auto_target_without_route_fails_closed():
    request = parse_import_command("nvftp=/nvidia-space/shared/team artifact=a", "nvis-ova")
    with pytest.raises(ValueError, match="no approved route"):
        resolve_target(request, Routing())


@pytest.mark.parametrize(
    "text",
    [
        "nvftp=/nvidia-space/shared/../private artifact=a target=tool",
        "nvftp=/nvidia-space/shared artifact='a;whoami' target=tool",
        "nvftp=/nvidia-space/shared artifact=a target=other-group/tool",
        "nvftp=/nvidia-space/shared artifact=a target=nvis-ova/nested/tool",
        "nvftp=/nvidia-space/shared artifact=a target=tool extra=x",
    ],
)
def test_parse_rejects_unsafe_input(text):
    with pytest.raises(ValueError):
        parse_import_command(text, "nvis-ova")


def test_allowed_source_uses_path_boundary():
    ensure_allowed_source("/nvidia-space/shared/team/project", ("/nvidia-space/shared/team",))
    with pytest.raises(PermissionError):
        ensure_allowed_source("/nvidia-space/shared/team-evil", ("/nvidia-space/shared/team",))
