"""Secure WSGI API and static-file server for the NVIS-OVA portal.

The API deliberately exposes read models through injected callables.  Mutation
handlers are individually registered, role checked, CSRF checked, and audited.
"""

from __future__ import annotations

import dataclasses
import json
import mimetypes
import os
import pathlib
import re
import secrets
import socketserver
import sqlite3
import urllib.parse
from collections.abc import Callable, Iterable, Mapping
from http import HTTPStatus
from typing import Protocol
from wsgiref.simple_server import WSGIServer, make_server

from .credentials import CredentialStore
from .rbac import (
    AuthenticationError,
    AuthorizationError,
    PasswordAuthenticator,
    Session,
    SessionCodec,
)

JsonObject = dict[str, object]
Reader = Callable[[], object]
_SAFE_UPLOAD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_ALLOWED_UPLOAD_SUFFIXES = {".bundle", ".gz", ".tgz", ".zip", ".pdf", ".json"}


class AuditHook(Protocol):
    def __call__(self, event: str, actor: str, details: Mapping[str, object]) -> None: ...


class GitLabReaders(Protocol):
    def repositories(self) -> object: ...

    def pipelines(self) -> object: ...

    def merge_requests(self) -> object: ...


def discard_audit(event: str, actor: str, details: Mapping[str, object]) -> None:
    """Explicit no-op suitable only for tests/development."""


@dataclasses.dataclass(frozen=True)
class PortalReaders:
    """Read-side integrations. Readers must return JSON-serializable values."""

    summary: Reader = dict
    overview: Reader = dict
    activity: Reader = list
    jobs: Reader = list
    repositories: Reader = list
    pipelines: Reader = list
    merge_requests: Reader = list
    approvals: Reader = list
    integrations: Reader = dict
    node: Reader = dict
    health: Reader = dict


class SqlitePortalReaders:
    """Safe read model for the existing JobStore database."""

    def __init__(self, database: pathlib.Path) -> None:
        self.database = database

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{urllib.parse.quote(str(self.database))}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def jobs(self, *, limit: int = 100) -> list[JsonObject]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT id, requester, channel, source, artifact, target, status,
                          result_url, created_at, updated_at
                   FROM jobs ORDER BY created_at DESC LIMIT ?""",
                (min(max(limit, 1), 500),),
            ).fetchall()
        return [dict(row) for row in rows]

    def activity(self, *, limit: int = 200) -> list[JsonObject]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT sequence, timestamp, job_id, event_type, actor, details_json,
                          previous_hash, event_hash
                   FROM audit_events ORDER BY sequence DESC LIMIT ?""",
                (min(max(limit, 1), 1000),),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(str(item.pop("details_json")))
            result.append(item)
        return result

    def summary(self) -> JsonObject:
        with self._connect() as connection:
            total = int(connection.execute("SELECT count(*) FROM jobs").fetchone()[0])
            by_status = {
                str(row[0]): int(row[1])
                for row in connection.execute(
                    "SELECT status, count(*) FROM jobs GROUP BY status"
                ).fetchall()
            }
            audit_events = int(
                connection.execute("SELECT count(*) FROM audit_events").fetchone()[0]
            )
        return {"jobs": total, "jobs_by_status": by_status, "audit_events": audit_events}


@dataclasses.dataclass(frozen=True)
class _Response:
    status: int
    body: bytes
    content_type: str = "application/json; charset=utf-8"
    headers: tuple[tuple[str, str], ...] = ()


class HubApplication:
    """WSGI application implementing authenticated portal endpoints."""

    def __init__(
        self,
        *,
        web_root: pathlib.Path,
        upload_root: pathlib.Path,
        max_upload_bytes: int,
        sessions: SessionCodec,
        authenticator: PasswordAuthenticator,
        audit: AuditHook,
        readers: PortalReaders | None = None,
        credentials: CredentialStore | None = None,
        secure_cookies: bool = True,
    ) -> None:
        self.web_root = web_root.resolve()
        self.upload_root = upload_root.resolve()
        self.upload_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.max_upload_bytes = max_upload_bytes
        self.sessions = sessions
        self.authenticator = authenticator
        self.readers = readers or PortalReaders()
        self.credentials = credentials
        self.audit = audit
        self.secure_cookies = secure_cookies

    def __call__(self, environ: dict[str, object], start_response: Callable) -> Iterable[bytes]:
        try:
            response = self._dispatch(environ)
        except AuthenticationError:
            response = self._json(401, {"error": "authentication_required"})
        except AuthorizationError as exc:
            response = self._json(403, {"error": "forbidden", "message": str(exc)})
        except (KeyError, TypeError, ValueError):
            response = self._json(400, {"error": "invalid_request"})
        except Exception:
            # Never reflect operational exceptions: they may contain URLs or credentials.
            response = self._json(500, {"error": "internal_error"})
        security_headers = (
            (
                "Content-Security-Policy",
                (
                    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                    "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; "
                    "base-uri 'none'; form-action 'self'"
                ),
            ),
            ("Referrer-Policy", "no-referrer"),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            ("Cache-Control", "no-store"),
        )
        headers = (
            ("Content-Type", response.content_type),
            ("Content-Length", str(len(response.body))),
            *security_headers,
            *response.headers,
        )
        start_response(f"{response.status} {HTTPStatus(response.status).phrase}", list(headers))
        return [response.body]

    def _dispatch(self, environ: dict[str, object]) -> _Response:
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))
        if method == "POST" and path == "/api/v1/auth/login":
            return self._login(environ)
        if path.startswith("/api/v1/"):
            session = self._session(environ)
            if method not in {"GET", "HEAD", "OPTIONS"}:
                self.sessions.verify_csrf(session, _header(environ, "X-CSRF-Token"))
            if method == "GET" and path == "/api/v1/auth/session":
                return self._json(200, self._session_json(session))
            if method == "POST" and path == "/api/v1/auth/logout":
                self.audit("auth.logout", session.principal.username, {})
                return self._json(200, {"ok": True}, clear_cookie=True)
            readers = {
                "/api/v1/summary": self.readers.summary,
                "/api/v1/overview": self.readers.overview,
                "/api/v1/activity": self.readers.activity,
                "/api/v1/audit": self.readers.activity,
                "/api/v1/jobs": self.readers.jobs,
                "/api/v1/repositories": self.readers.repositories,
                "/api/v1/pipelines": self.readers.pipelines,
                "/api/v1/merge-requests": self.readers.merge_requests,
                "/api/v1/approvals": self.readers.approvals,
                "/api/v1/integrations": self.readers.integrations,
                "/api/v1/node": self.readers.node,
                "/api/v1/health": self.readers.health,
            }
            if method == "GET" and path in readers:
                return self._json(200, readers[path]())
            if method == "GET" and path == "/api/v1/credentials":
                session.principal.require("admin")
                return self._json(
                    200, {"data": self.credentials.configured() if self.credentials else {}}
                )
            if method == "POST" and path.startswith("/api/v1/credentials/"):
                return self._rotate_credential(environ, session, path.rsplit("/", 1)[-1])
            if method == "POST" and path == "/api/v1/uploads":
                return self._upload(environ, session)
            return self._json(405 if path in readers else 404, {"error": "not_found"})
        if method != "GET":
            return self._json(405, {"error": "method_not_allowed"})
        return self._static(path)

    def _login(self, environ: dict[str, object]) -> _Response:
        body = self._json_body(environ, maximum=16_384)
        principal = self.authenticator.authenticate(
            str(body.get("username", "")), str(body.get("password", ""))
        )
        token, session = self.sessions.issue(principal)
        self.audit("auth.login", principal.username, {})
        return self._json(
            200,
            self._session_json(session),
            cookie=(
                f"nvis_session={token}; Path=/; Max-Age=3600; HttpOnly; "
                f"{'Secure; ' if self.secure_cookies else ''}SameSite=Strict"
            ),
        )

    def _rotate_credential(
        self, environ: dict[str, object], session: Session, name: str
    ) -> _Response:
        session.principal.require("admin")
        if self.credentials is None:
            raise KeyError(name)
        body = self._json_body(environ, maximum=64_000)
        self.audit("credential.rotate.requested", session.principal.username, {"name": name})
        self.credentials.rotate(name, str(body.get("value", "")))
        self.audit("credential.rotated", session.principal.username, {"name": name})
        return self._json(200, {"ok": True, "name": name, "configured": True})

    def _upload(self, environ: dict[str, object], session: Session) -> _Response:
        session.principal.require("operator")
        content_type = str(environ.get("CONTENT_TYPE", "")).split(";", 1)[0]
        if content_type != "application/octet-stream":
            raise ValueError("binary upload required")
        query = urllib.parse.parse_qs(str(environ.get("QUERY_STRING", "")))
        filename = query.get("filename", [""])[0]
        if not _SAFE_UPLOAD.fullmatch(filename) or not any(
            filename.endswith(suffix) for suffix in _ALLOWED_UPLOAD_SUFFIXES
        ):
            raise ValueError("unsafe upload filename")
        length = _content_length(environ)
        if length <= 0 or length > self.max_upload_bytes:
            return self._json(413, {"error": "upload_too_large"})
        upload_id = secrets.token_hex(12)
        target = self.upload_root / f"{upload_id}-{filename}"
        stream = environ["wsgi.input"]
        descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            remaining = length
            with os.fdopen(descriptor, "wb") as output:
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))  # type: ignore[attr-defined]
                    if not chunk:
                        raise ValueError("truncated upload")
                    output.write(chunk)
                    remaining -= len(chunk)
                output.flush()
                os.fsync(output.fileno())
        except Exception:
            target.unlink(missing_ok=True)
            raise
        try:
            self.audit(
                "upload.staged",
                session.principal.username,
                {"upload_id": upload_id, "filename": filename, "bytes": length},
            )
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return self._json(201, {"upload_id": upload_id, "filename": filename, "bytes": length})

    def _static(self, request_path: str) -> _Response:
        relative = urllib.parse.unquote(request_path).lstrip("/") or "index.html"
        candidate = (self.web_root / relative).resolve()
        if candidate != self.web_root and self.web_root not in candidate.parents:
            return self._json(404, {"error": "not_found"})
        if not candidate.is_file():
            # SPA navigation fallback, but never for files with extensions.
            if "." not in pathlib.PurePosixPath(relative).name:
                candidate = self.web_root / "index.html"
            if not candidate.is_file():
                return self._json(404, {"error": "not_found"})
        media_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        return _Response(200, candidate.read_bytes(), media_type)

    def _session(self, environ: dict[str, object]) -> Session:
        cookies = _parse_cookies(str(environ.get("HTTP_COOKIE", "")))
        return self.sessions.verify(cookies.get("nvis_session", ""))

    def _json_body(self, environ: dict[str, object], *, maximum: int) -> JsonObject:
        if str(environ.get("CONTENT_TYPE", "")).split(";", 1)[0] != "application/json":
            raise ValueError("JSON required")
        length = _content_length(environ)
        if length <= 0 or length > maximum:
            raise ValueError("invalid body length")
        raw = environ["wsgi.input"].read(length)  # type: ignore[attr-defined]
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise TypeError("JSON object required")
        return result

    @staticmethod
    def _session_json(session: Session) -> JsonObject:
        return {
            "user": session.principal.username,
            "display_name": session.principal.display_name,
            "role": session.principal.role,
            "csrf_token": session.csrf_token,
            "expires_at": session.expires_at,
        }

    def _json(
        self,
        status: int,
        value: object,
        *,
        cookie: str | None = None,
        clear_cookie: bool = False,
    ) -> _Response:
        headers: list[tuple[str, str]] = []
        if cookie:
            headers.append(("Set-Cookie", cookie))
        if clear_cookie:
            headers.append(
                (
                    "Set-Cookie",
                    (
                        "nvis_session=; Path=/; Max-Age=0; HttpOnly; "
                        f"{'Secure; ' if self.secure_cookies else ''}SameSite=Strict"
                    ),
                )
            )
        return _Response(
            status,
            json.dumps(value, separators=(",", ":"), sort_keys=True).encode(),
            headers=tuple(headers),
        )


def _parse_cookies(raw: str) -> dict[str, str]:
    cookies = {}
    for item in raw.split(";"):
        if "=" in item:
            name, value = item.strip().split("=", 1)
            cookies[name] = value
    return cookies


def _header(environ: dict[str, object], name: str) -> str | None:
    return environ.get("HTTP_" + name.upper().replace("-", "_"))  # type: ignore[return-value]


def _content_length(environ: dict[str, object]) -> int:
    try:
        return int(str(environ.get("CONTENT_LENGTH", "")))
    except ValueError as exc:
        raise ValueError("valid Content-Length required") from exc


def live_readers(
    *,
    state: SqlitePortalReaders,
    gitlab: GitLabReaders,
    integrations: Reader,
    node: Reader,
) -> PortalReaders:
    """Compose the normal live read model without coupling to configuration or CLI."""
    return PortalReaders(
        summary=state.summary,
        overview=state.summary,
        activity=state.activity,
        jobs=state.jobs,
        repositories=gitlab.repositories,
        pipelines=gitlab.pipelines,
        merge_requests=gitlab.merge_requests,
        integrations=integrations,
        node=node,
        health=lambda: {"integrations": integrations(), "node": node()},
    )


def serve_localhost(
    application: HubApplication,
    *,
    port: int = 8787,
    host: str = "127.0.0.1",
    allow_network: bool = False,
) -> WSGIServer:
    """Create a WSGI server; network binding requires an explicit opt-in."""
    if host not in {"127.0.0.1", "localhost"} and not allow_network:
        raise ValueError("network portal bind requires allow_network=True")
    if not 1 <= port <= 65535:
        raise ValueError("invalid port")
    class ThreadedWSGIServer(socketserver.ThreadingMixIn, WSGIServer):
        daemon_threads = True

    return make_server(host, port, application, server_class=ThreadedWSGIServer)
