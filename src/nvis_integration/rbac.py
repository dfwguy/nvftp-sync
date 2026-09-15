"""Small, dependency-free authentication and RBAC primitives for the local portal."""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Mapping

ROLE_LEVEL = {"viewer": 10, "operator": 20, "approver": 30, "admin": 40}


class AuthenticationError(ValueError):
    """An authentication token or credential was invalid."""


class AuthorizationError(PermissionError):
    """An authenticated principal lacks the required role."""


@dataclasses.dataclass(frozen=True)
class Principal:
    username: str
    role: str
    display_name: str | None = None

    def __post_init__(self) -> None:
        if self.role not in ROLE_LEVEL:
            raise ValueError(f"unknown role: {self.role}")
        if self.display_name is not None and (
            not self.display_name.strip()
            or len(self.display_name) > 160
            or any(ord(character) < 32 for character in self.display_name)
        ):
            raise ValueError("invalid display name")

    def require(self, minimum_role: str) -> None:
        if minimum_role not in ROLE_LEVEL:
            raise ValueError(f"unknown role: {minimum_role}")
        if ROLE_LEVEL[self.role] < ROLE_LEVEL[minimum_role]:
            raise AuthorizationError(f"{minimum_role} role required")


class PasswordAuthenticator:
    """Authenticate against scrypt password records held outside application code."""

    def __init__(self, records: Mapping[str, tuple[str, str] | tuple[str, str, str]]) -> None:
        self._records = dict(records)

    @staticmethod
    def password_record(password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
        return "scrypt$" + base64.urlsafe_b64encode(salt + digest).decode()

    def authenticate(self, username: str, password: str) -> Principal:
        record = self._records.get(username)
        # Do equivalent work for missing users to reduce username timing leakage.
        fallback = ("viewer", self.password_record("invalid-password"), "Unknown user")
        supplied = record or fallback
        role, encoded = supplied[:2]
        display_name = supplied[2] if len(supplied) == 3 else None
        try:
            algorithm, value = encoded.split("$", 1)
            raw = base64.urlsafe_b64decode(value.encode())
            salt, expected = raw[:16], raw[16:]
            actual = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
        except (ValueError, TypeError) as exc:
            raise AuthenticationError("invalid credentials") from exc
        if algorithm != "scrypt" or record is None or not hmac.compare_digest(actual, expected):
            raise AuthenticationError("invalid credentials")
        return Principal(username, role, display_name)


@dataclasses.dataclass(frozen=True)
class Session:
    principal: Principal
    csrf_token: str
    expires_at: int


class SessionCodec:
    """Issue and verify short-lived HMAC-authenticated session cookies."""

    def __init__(self, secret: bytes, *, lifetime_seconds: int = 3600) -> None:
        if len(secret) < 32:
            raise ValueError("session signing secret must be at least 32 bytes")
        self._secret = secret
        self._lifetime = lifetime_seconds

    def issue(self, principal: Principal, *, now: int | None = None) -> tuple[str, Session]:
        issued = int(time.time() if now is None else now)
        session = Session(principal, secrets.token_urlsafe(24), issued + self._lifetime)
        payload = json.dumps(
            {
                "sub": principal.username,
                "role": principal.role,
                "name": principal.display_name,
                "csrf": session.csrf_token,
                "exp": session.expires_at,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        encoded = _b64(payload)
        signature = _b64(hmac.digest(self._secret, encoded.encode(), "sha256"))
        return f"{encoded}.{signature}", session

    def verify(self, token: str, *, now: int | None = None) -> Session:
        try:
            encoded, supplied_signature = token.split(".", 1)
            expected_signature = _b64(hmac.digest(self._secret, encoded.encode(), "sha256"))
            if not hmac.compare_digest(supplied_signature, expected_signature):
                raise AuthenticationError("invalid session")
            payload = json.loads(_unb64(encoded))
            display_name = payload.get("name")
            principal = Principal(
                str(payload["sub"]),
                str(payload["role"]),
                str(display_name) if display_name is not None else None,
            )
            session = Session(principal, str(payload["csrf"]), int(payload["exp"]))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise AuthenticationError("invalid session") from exc
        current = int(time.time() if now is None else now)
        if current >= session.expires_at:
            raise AuthenticationError("session expired")
        return session

    @staticmethod
    def verify_csrf(session: Session, supplied: str | None) -> None:
        if supplied is None or not hmac.compare_digest(session.csrf_token, supplied):
            raise AuthorizationError("valid CSRF token required")


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
