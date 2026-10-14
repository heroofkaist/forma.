"""Verified accounts, opaque sessions and single-use email actions."""
import hashlib
import os
import re
import secrets
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage
from urllib.parse import urlencode

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from account_models import Account, AccountAction, AccountSession, RateBucket
from persistence import SessionLocal, now_utc
from auth import AuthUser, auth_required, request_user
from email_delivery import enqueue_action

router = APIRouter(prefix="/api/accounts", tags=["Accounts"])
# OWASP minimum Argon2id memory profile, suitable for the existing small host.
hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))
SESSION_SECONDS = 8 * 60 * 60


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def utc(value):
    from datetime import timezone
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def mail_configured() -> bool:
    from email_delivery import cipher
    try:
        cipher()
    except (KeyError, ValueError):
        return False
    return all(os.getenv(key) for key in ("FORMA_SMTP_HOST", "FORMA_SMTP_USERNAME", "FORMA_SMTP_PASSWORD", "FORMA_EMAIL_FROM", "FORMA_EMAIL_TOKEN_KEY", "FRONTEND_ORIGIN"))


def registration_enabled() -> bool:
    return auth_required() and os.getenv("FORMA_PUBLIC_REGISTRATION", "false").lower() == "true" and mail_configured()


def require_email():
    if not mail_configured():
        raise HTTPException(503, "Transactional email is not configured. Contact the administrator.")


def rate_limit(request: Request, action: str, identity: str = "", limit: int = 10):
    # No trust in client-supplied X-Forwarded-For. Per-identity limits also apply
    # through the BFF, whose outgoing IP is shared by its users.
    address = request.client.host if request.client else "unknown"
    window = int(now_utc().timestamp()) // 900
    keys = [digest(f"{action}:ip:{address}:{window}")]
    limits = [max(limit * 20, 100)]
    if identity:
        keys.append(digest(f"{action}:identity:{identity.casefold()}:{window}"))
        limits.append(limit)
    with SessionLocal() as db:
        db.execute(delete(RateBucket).where(RateBucket.expires_at < now_utc()))
        insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
        for key, maximum in zip(keys, limits):
            statement = insert(RateBucket).values(key=key, count=1, expires_at=now_utc() + timedelta(minutes=30))
            count = db.scalar(statement.on_conflict_do_update(index_elements=[RateBucket.key], set_={"count": RateBucket.count + 1}).returning(RateBucket.count))
            if count > maximum:
                db.commit()
                raise HTTPException(429, "Too many attempts. Try again later.", headers={"Retry-After": "900"})
        db.commit()


def send_action(email: str, purpose: str, token: str):
    require_email()
    origin = os.environ["FRONTEND_ORIGIN"].rstrip("/")
    if not origin.startswith("https://") and not origin.startswith("http://localhost:"):
        raise HTTPException(503, "FRONTEND_ORIGIN must be an HTTPS frontend URL.")
    route = "teacher-invitation" if purpose == "teacher_invite" else "verify-email" if purpose == "verify" else "reset-password"
    message = EmailMessage()
    message["From"] = os.environ["FORMA_EMAIL_FROM"]
    message["To"] = email
    message["Subject"] = "Forma — teacher invitation" if purpose == "teacher_invite" else "Forma — verify your email" if purpose == "verify" else "Forma — reset your password"
    message.set_content(f"Open this single-use link within one hour:\n{origin}/{route}?{urlencode({'token': token})}\n\nIf you did not request this, ignore this email.")
    try:
        with smtplib.SMTP(os.environ["FORMA_SMTP_HOST"], int(os.getenv("FORMA_SMTP_PORT", "587")), timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(os.environ["FORMA_SMTP_USERNAME"], os.environ["FORMA_SMTP_PASSWORD"])
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise HTTPException(503, "Email delivery failed. Please try again later.") from exc


def issue_action(db, account: Account, purpose: str):
    token = secrets.token_urlsafe(32)
    db.execute(delete(AccountAction).where(AccountAction.account_id == account.id, AccountAction.purpose == purpose))
    db.add(AccountAction(token_hash=digest(token), account_id=account.id, purpose=purpose, expires_at=now_utc() + timedelta(hours=1)))
    enqueue_action(db, account, purpose, token)


class EmailPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        value = value.strip().casefold()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address.")
        return value


class RegisterPayload(EmailPayload):
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=256)

    @field_validator("display_name")
    @classmethod
    def name(cls, value):
        if not value.strip():
            raise ValueError("Display name is required.")
        return value.strip()


class ActionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=100)


class ResetPayload(ActionPayload):
    password: str = Field(min_length=12, max_length=256)


class ProfilePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=200)


class PasswordPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=12, max_length=256)


def account_identity(request: Request) -> str:
    user = request_user(request)
    if not user.account_id:
        raise HTTPException(403, "A verified account is required for this workflow.")
    return user.account_id


def password_matches(encoded: str, password: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def account_login(email: str, password: str) -> AuthUser | None:
    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == email.strip().casefold()))
        valid = password_matches(account.password_hash if account else DUMMY_HASH, password)
        if not valid or not account or not account.verified or account.status != "active":
            return None
        if hasher.check_needs_rehash(account.password_hash):
            account.password_hash = hasher.hash(password)
        account.last_login_at = now_utc()
        db.commit()
        from institutions import effective_role
        role = effective_role(db, account.id)
        return AuthUser(role=role, username=account.email, student_id=account.id if role == "student" else None, account_id=account.id)


def create_session(user: AuthUser) -> str:
    token = "acct_" + secrets.token_urlsafe(32)
    with SessionLocal() as db:
        db.execute(delete(AccountSession).where(AccountSession.expires_at < now_utc()))
        db.add(AccountSession(token_hash=digest(token), account_id=user.account_id, expires_at=now_utc() + timedelta(seconds=SESSION_SECONDS)))
        db.commit()
    return token


def verify_session(token: str) -> AuthUser:
    with SessionLocal() as db:
        session = db.get(AccountSession, digest(token))
        account = db.get(Account, session.account_id) if session else None
        if not session or utc(session.expires_at) <= now_utc() or not account or not account.verified or account.status != "active":
            raise HTTPException(401, "Invalid or expired session.")
        from institutions import effective_role
        role = effective_role(db, account.id)
        return AuthUser(role=role, username=account.email, student_id=account.id if role == "student" else None, account_id=account.id)


@router.get("/status")
def status():
    return {"registration_enabled": registration_enabled(), "email_configured": mail_configured()}


@router.post("/register", status_code=202)
def register(payload: RegisterPayload, request: Request):
    rate_limit(request, "register", payload.email, 5)
    if not registration_enabled():
        raise HTTPException(503, "Public registration is disabled or transactional email is not configured.")
    password_hash = hasher.hash(payload.password)
    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == payload.email))
        if account is None:
            account = Account(email=payload.email, display_name=payload.display_name, password_hash=password_hash)
            db.add(account)
            try:
                db.flush()
            except Exception as exc:
                from sqlalchemy.exc import IntegrityError
                if not isinstance(exc, IntegrityError):
                    raise
                db.rollback()
                return {"message": "If this address is eligible, a verification email has been queued for delivery."}
            from institution_models import AccountRole
            db.add(AccountRole(account_id=account.id, role="student"))
            issue_action(db, account, "verify")
            db.commit()
    return {"message": "If this address is eligible, a verification email has been queued for delivery."}


@router.post("/verify-email")
def verify_email(payload: ActionPayload, request: Request):
    rate_limit(request, "verify", digest(payload.token), 10)
    with SessionLocal() as db:
        account_id = db.scalar(delete(AccountAction).where(AccountAction.token_hash == digest(payload.token), AccountAction.purpose == "verify", AccountAction.expires_at > now_utc()).returning(AccountAction.account_id))
        if not account_id:
            raise HTTPException(400, "Invalid or expired link.")
        db.execute(update(Account).where(Account.id == account_id).values(verified=True, updated_at=now_utc()))
        db.commit()
    return {"message": "Email verified. You can now sign in."}


@router.post("/forgot-password", status_code=202)
def forgot_password(payload: EmailPayload, request: Request):
    rate_limit(request, "reset-request", payload.email, 5)
    require_email()
    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == payload.email, Account.verified.is_(True), Account.status == "active"))
        if account:
            issue_action(db, account, "reset")
            db.commit()
    return {"message": "If the account is eligible, a reset email has been queued for delivery."}


@router.post("/resend-verification", status_code=202)
def resend_verification(payload: EmailPayload, request: Request):
    rate_limit(request, "verify-request", payload.email, 5)
    require_email()
    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.email == payload.email, Account.verified.is_(False), Account.status == "active"))
        if account:
            from institution_models import AccountRole
            db.add(AccountRole(account_id=account.id, role="student"))
            issue_action(db, account, "verify")
            db.commit()
    return {"message": "If the account is eligible, a verification email has been queued for delivery."}


@router.post("/reset-password")
def reset_password(payload: ResetPayload, request: Request):
    rate_limit(request, "reset", digest(payload.token), 10)
    encoded = hasher.hash(payload.password)
    with SessionLocal() as db:
        account_id = db.scalar(delete(AccountAction).where(AccountAction.token_hash == digest(payload.token), AccountAction.purpose == "reset", AccountAction.expires_at > now_utc()).returning(AccountAction.account_id))
        if not account_id:
            raise HTTPException(400, "Invalid or expired link.")
        db.execute(update(Account).where(Account.id == account_id).values(password_hash=encoded, updated_at=now_utc()))
        db.execute(delete(AccountSession).where(AccountSession.account_id == account_id))
        db.commit()
    return {"message": "Password updated. Please sign in again."}


@router.post("/logout")
def logout(request: Request):
    account_identity(request)
    token = request.headers.get("authorization", "").partition(" ")[2]
    with SessionLocal() as db:
        db.execute(delete(AccountSession).where(AccountSession.token_hash == digest(token)))
        db.commit()
    return {"message": "Signed out."}


@router.get("/profile")
def profile(request: Request):
    with SessionLocal() as db:
        account = db.get(Account, account_identity(request))
        return {"email": account.email, "display_name": account.display_name, "verified": account.verified}


@router.patch("/profile")
def update_profile(payload: ProfilePayload, request: Request):
    if not payload.display_name.strip():
        raise HTTPException(422, "Display name is required.")
    with SessionLocal() as db:
        account = db.get(Account, account_identity(request))
        account.display_name = payload.display_name.strip()
        db.commit()
    return {"message": "Profile saved."}


@router.post("/password")
def change_password(payload: PasswordPayload, request: Request):
    identity = account_identity(request)
    rate_limit(request, "change-password", identity, 5)
    with SessionLocal() as db:
        account = db.get(Account, identity)
        if not password_matches(account.password_hash, payload.current_password):
            raise HTTPException(400, "Current password is incorrect.")
        account.password_hash = hasher.hash(payload.password)
        db.execute(delete(AccountSession).where(AccountSession.account_id == identity))
        db.commit()
    return {"message": "Password updated. All sessions have been signed out."}
