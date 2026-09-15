"""Deterministic source-to-project routing; AI recommendations never bypass this policy."""

from __future__ import annotations

from .config import Routing
from .models import ImportRequest


def resolve_target(request: ImportRequest, routing: Routing) -> ImportRequest:
    """Resolve ``target=auto`` from an operator-reviewed exact-path catalog."""
    if request.target != "auto":
        return request
    target = routing.exact_sources.get(request.source.rstrip("/"))
    if target is None:
        raise ValueError(
            "no approved route exists for this NVFTP source; supply target= or add an exact route"
        )
    return ImportRequest(source=request.source, artifact=request.artifact, target=target)
