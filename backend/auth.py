import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request

TOKEN_LIFETIME_SECONDS = 8 * 60 * 60
_STUDENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


@dataclass(frozen=True)
class AuthUser:
    role: str
    username: str
    student_id: str | None = None


def auth_required() -> bool:
    value = os.getenv("FORMA_AUTH_REQUIRED", "false").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False
    raise RuntimeError("FORMA_AUTH_REQUIRED must be a boolean value.")


def _student_credentials() -> dict[str, str]:
    raw = os.getenv("FORMA_STUDENT_CREDENTIALS_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("FORMA_STUDENT_CREDENTIALS_JSON must be valid JSON.") from exc
    if not isinstance(parsed, dict) or any(
        not isinstance(student_id, str)
        or not _STUDENT_ID_PATTERN.fullmatch(student_id)
        or not isinstance(password, str)
        or not password
        for student_id, password in parsed.items()
    ):
        raise RuntimeError(
            "FORMA_STUDENT_CREDENTIALS_JSON must map student IDs to non-empty passwords."
        )
    return parsed


def validate_auth_configuration() -> None:
    if not auth_required():
        return
    secret = os.getenv("FORMA_AUTH_SECRET", "")
    if len(secret.encode("utf-8")) < 32:
        raise RuntimeError("FORMA_AUTH_SECRET must contain at least 32 bytes when auth is enabled.")
    if not os.getenv("FORMA_TEACHER_USERNAME", "").strip():
        raise RuntimeError("FORMA_TEACHER_USERNAME is required when auth is enabled.")
    teacher_password = os.getenv("FORMA_TEACHER_PASSWORD", "")
    if len(teacher_password) < 12:
        raise RuntimeError(
            "FORMA_TEACHER_PASSWORD must contain at least 12 characters when auth is enabled."
        )
    student_credentials = _student_credentials()
    if not student_credentials:
        raise RuntimeError("At least one student credential is required when auth is enabled.")
    if any(len(password) < 12 for password in student_credentials.values()):
        raise RuntimeError(
            "Student passwords must contain at least 12 characters when auth is enabled."
        )


def _secret() -> bytes:
    secret = os.getenv("FORMA_AUTH_SECRET", "").encode("utf-8")
    if len(secret) < 32:
        raise RuntimeError("FORMA_AUTH_SECRET must contain at least 32 bytes.")
    return secret


def _constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.b64decode(
        value + "=" * (-len(value) % 4),
        altchars=b"-_",
        validate=True,
    )


def create_token(user: AuthUser) -> str:
    payload = {
        "role": user.role,
        "username": user.username,
        "student_id": user.student_id,
        "exp": int(time.time()) + TOKEN_LIFETIME_SECONDS,
    }
    body = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _encode(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def verify_token(token: str) -> AuthUser:
    try:
        if len(token) > 4096:
            raise ValueError("Token is too long.")
        body, signature = token.split(".", 1)
        expected = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _decode(signature)):
            raise ValueError("Invalid token signature.")
        payload = json.loads(_decode(body))
        if not isinstance(payload, dict) or int(payload["exp"]) <= int(time.time()):
            raise ValueError("Expired token.")
        role = payload["role"]
        username = payload["username"]
        student_id = payload.get("student_id")
        if role not in {"teacher", "student"} or not isinstance(username, str):
            raise ValueError("Invalid token claims.")
        if (role == "student") != isinstance(student_id, str):
            raise ValueError("Invalid token identity.")
        if role == "teacher" and not _constant_time_equal(
            username, os.getenv("FORMA_TEACHER_USERNAME", "")
        ):
            raise ValueError("Teacher account is no longer configured.")
        if role == "student" and student_id not in _student_credentials():
            raise ValueError("Student account is no longer configured.")
        return AuthUser(role=role, username=username, student_id=student_id)
    except (
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        binascii.Error,
    ) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired bearer token.") from exc


def authenticate(role: str, username: str, password: str) -> AuthUser | None:
    if role == "teacher":
        valid_username = _constant_time_equal(
            username, os.getenv("FORMA_TEACHER_USERNAME", "")
        )
        valid_password = _constant_time_equal(
            password, os.getenv("FORMA_TEACHER_PASSWORD", "")
        )
        return AuthUser(role="teacher", username=username) if valid_username and valid_password else None
    if role == "student":
        credentials = _student_credentials()
        expected = credentials.get(username)
        if expected is not None and _constant_time_equal(password, expected):
            return AuthUser(role="student", username=username, student_id=username)
    return None


def request_user(request: Request) -> AuthUser:
    user = getattr(request.state, "auth_user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user
