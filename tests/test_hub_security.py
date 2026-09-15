from __future__ import annotations

import io
import json
import os
import pathlib

import pytest

from nvis_integration.credentials import CredentialStore
from nvis_integration.hub_api import HubApplication, PortalReaders, serve_localhost
from nvis_integration.rbac import (
    AuthenticationError,
    AuthorizationError,
    PasswordAuthenticator,
    Principal,
    SessionCodec,
)


def test_role_hierarchy() -> None:
    Principal("alice", "admin").require("approver")
    Principal("bob", "operator").require("viewer")
    with pytest.raises(AuthorizationError):
        Principal("bob", "operator").require("approver")


def test_signed_session_expiry_and_tamper() -> None:
    codec = SessionCodec(b"s" * 32, lifetime_seconds=60)
    token, session = codec.issue(Principal("alice", "operator"), now=100)
    assert codec.verify(token, now=159).principal.username == "alice"
    codec.verify_csrf(session, session.csrf_token)
    with pytest.raises(AuthenticationError):
        codec.verify(token + "x", now=101)
    with pytest.raises(AuthenticationError, match="expired"):
        codec.verify(token, now=160)
    with pytest.raises(AuthorizationError):
        codec.verify_csrf(session, "wrong")


def test_password_authentication() -> None:
    record = PasswordAuthenticator.password_record("correct horse")
    auth = PasswordAuthenticator({"alice": ("approver", record, "Alice Example")})
    assert auth.authenticate("alice", "correct horse") == Principal(
        "alice", "approver", "Alice Example"
    )
    with pytest.raises(AuthenticationError):
        auth.authenticate("alice", "wrong")
    with pytest.raises(AuthenticationError):
        auth.authenticate("missing", "correct horse")


def test_signed_session_preserves_display_name() -> None:
    codec = SessionCodec(b"s" * 32)
    token, _ = codec.issue(Principal("alice@example.com", "operator", "Alice Example"))
    assert codec.verify(token).principal.display_name == "Alice Example"


def test_credential_rotation_is_atomic_private_and_never_listed(tmp_path: pathlib.Path) -> None:
    store = CredentialStore(tmp_path / "secrets", {"gitlab-token", "slack-token"})
    store.rotate("gitlab-token", "first")
    store.rotate("gitlab-token", "second")
    target = store.path("gitlab-token")
    assert target.read_text() == "second\n"
    assert target.stat().st_mode & 0o777 == 0o600
    assert store.configured() == {"gitlab-token": True, "slack-token": False}
    with pytest.raises(KeyError):
        store.rotate("../escape", "secret")
    with pytest.raises(ValueError):
        store.rotate("gitlab-token", "two\nlines")


def _request(
    app: HubApplication,
    method: str,
    path: str,
    *,
    body: bytes = b"",
    content_type: str = "application/json",
    cookie: str = "",
    csrf: str = "",
    query: str = "",
) -> tuple[int, dict[str, str], bytes]:
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

    environ: dict[str, object] = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": content_type,
        "HTTP_COOKIE": cookie,
        "HTTP_X_CSRF_TOKEN": csrf,
        "wsgi.input": io.BytesIO(body),
    }
    response_body = b"".join(app(environ, start_response))
    headers = {str(key): str(value) for key, value in captured["headers"]}  # type: ignore[index]
    return int(str(captured["status"]).split()[0]), headers, response_body


@pytest.fixture
def portal(tmp_path: pathlib.Path) -> tuple[HubApplication, list[tuple[str, str, object]]]:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("portal")
    password = PasswordAuthenticator.password_record("password")
    events: list[tuple[str, str, object]] = []
    app = HubApplication(
        web_root=web,
        upload_root=tmp_path / "uploads",
        max_upload_bytes=32,
        sessions=SessionCodec(b"x" * 32),
        authenticator=PasswordAuthenticator(
            {
                "viewer": ("viewer", password),
                "admin": ("admin", password),
                "operator": ("operator", password),
            }
        ),
        audit=lambda event, actor, details: events.append((event, actor, details)),
        readers=PortalReaders(summary=lambda: {"jobs": 7}),
        credentials=CredentialStore(tmp_path / "credentials", {"gitlab-token"}),
    )
    return app, events


def _login(app: HubApplication, username: str) -> tuple[str, str]:
    status, headers, raw = _request(
        app,
        "POST",
        "/api/v1/auth/login",
        body=json.dumps({"username": username, "password": "password"}).encode(),
    )
    assert status == 200
    assert "HttpOnly; Secure; SameSite=Strict" in headers["Set-Cookie"]
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    return cookie, json.loads(raw)["csrf_token"]


def test_api_requires_auth_and_enforces_csrf_and_roles(portal) -> None:
    app, events = portal
    status, _, _ = _request(app, "GET", "/api/v1/summary")
    assert status == 401
    cookie, csrf = _login(app, "viewer")
    status, headers, raw = _request(app, "GET", "/api/v1/summary", cookie=cookie)
    assert status == 200
    assert json.loads(raw) == {"jobs": 7}
    assert headers["X-Frame-Options"] == "DENY"
    status, _, _ = _request(
        app,
        "POST",
        "/api/v1/credentials/gitlab-token",
        body=b'{"value":"must-not-leak"}',
        cookie=cookie,
        csrf=csrf,
    )
    assert status == 403
    admin_cookie, _ = _login(app, "admin")
    status, _, _ = _request(
        app,
        "POST",
        "/api/v1/credentials/gitlab-token",
        body=b'{"value":"must-not-leak"}',
        cookie=admin_cookie,
        csrf="wrong",
    )
    assert status == 403
    assert all("must-not-leak" not in repr(event) for event in events)


def test_logout_clears_browser_session_and_writes_audit_event(portal) -> None:
    app, events = portal
    cookie, csrf = _login(app, "operator")
    status, headers, raw = _request(
        app,
        "POST",
        "/api/v1/auth/logout",
        cookie=cookie,
        csrf=csrf,
    )
    assert status == 200
    assert json.loads(raw) == {"ok": True}
    assert "Max-Age=0" in headers["Set-Cookie"]
    assert ("auth.logout", "operator", {}) in events


def test_admin_rotates_credential_without_secret_in_response_or_audit(portal) -> None:
    app, events = portal
    cookie, csrf = _login(app, "admin")
    secret = "glpat-a-highly-sensitive-value"
    status, _, raw = _request(
        app,
        "POST",
        "/api/v1/credentials/gitlab-token",
        body=json.dumps({"value": secret}).encode(),
        cookie=cookie,
        csrf=csrf,
    )
    assert status == 200
    assert secret.encode() not in raw
    assert secret not in repr(events)
    assert (app.credentials.path("gitlab-token")).read_text().strip() == secret  # type: ignore[union-attr]


def test_upload_is_bounded_private_and_audited(portal) -> None:
    app, events = portal
    cookie, csrf = _login(app, "operator")
    status, _, raw = _request(
        app,
        "POST",
        "/api/v1/uploads",
        body=b"bundle",
        content_type="application/octet-stream",
        cookie=cookie,
        csrf=csrf,
        query="filename=release.bundle",
    )
    assert status == 201
    result = json.loads(raw)
    target = next(app.upload_root.iterdir())
    assert target.name.endswith("-release.bundle")
    assert target.read_bytes() == b"bundle"
    assert os.stat(target).st_mode & 0o777 == 0o600
    assert events[-1][0] == "upload.staged"
    status, _, _ = _request(
        app,
        "POST",
        "/api/v1/uploads",
        body=b"x" * 33,
        content_type="application/octet-stream",
        cookie=cookie,
        csrf=csrf,
        query="filename=big.bundle",
    )
    assert status == 413
    assert result["filename"] == "release.bundle"


def test_static_path_traversal_is_rejected(portal, tmp_path: pathlib.Path) -> None:
    app, _ = portal
    status, _, raw = _request(app, "GET", "/")
    assert status == 200 and raw == b"portal"
    status, _, _ = _request(app, "GET", "/%2e%2e/secret")
    assert status == 404


def test_server_refuses_non_local_bind(portal) -> None:
    app, _ = portal
    with pytest.raises(ValueError, match="allow_network"):
        serve_localhost(app, host="0.0.0.0")


def test_internal_http_mode_omits_secure_cookie(tmp_path: pathlib.Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("portal")
    password = PasswordAuthenticator.password_record("password")
    app = HubApplication(
        web_root=web,
        upload_root=tmp_path / "uploads",
        max_upload_bytes=32,
        sessions=SessionCodec(b"x" * 32),
        authenticator=PasswordAuthenticator({"admin": ("admin", password)}),
        audit=lambda _event, _actor, _details: None,
        secure_cookies=False,
    )
    status, headers, _ = _request(
        app,
        "POST",
        "/api/v1/auth/login",
        body=json.dumps({"username": "admin", "password": "password"}).encode(),
    )
    assert status == 200
    assert "HttpOnly; SameSite=Strict" in headers["Set-Cookie"]
    assert "Secure" not in headers["Set-Cookie"]
