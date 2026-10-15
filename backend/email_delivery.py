"""Durable encrypted mail outbox; no provider calls on account discovery paths."""
import os
import threading
from datetime import timedelta
from uuid import uuid4
from cryptography.fernet import Fernet
from sqlalchemy import or_, select, update
from account_models import Account, AccountAction, EmailOutbox
from persistence import SessionLocal, now_utc

TRANSACTIONAL_PURPOSES = frozenset({"verify", "reset", "teacher_invite"})


def require_transactional_purpose(purpose):
    if purpose not in TRANSACTIONAL_PURPOSES:
        raise ValueError("Only account-action mail is supported. Marketing email is disabled.")


def cipher():
    return Fernet(os.environ["FORMA_EMAIL_TOKEN_KEY"].encode())


def enqueue_action(db, account, purpose, token):
    require_transactional_purpose(purpose)
    db.add(EmailOutbox(account_id=account.id, purpose=purpose, encrypted_token=cipher().encrypt(token.encode()).decode(), expires_at=now_utc() + timedelta(hours=1)))


def deliver_one():
    from accounts import digest, send_action
    lease_id = str(uuid4())
    now = now_utc()
    with SessionLocal() as db:
        db.execute(update(EmailOutbox).where(EmailOutbox.status.in_(["queued", "sending"]), or_(EmailOutbox.expires_at <= now, (EmailOutbox.attempts >= 3) & (EmailOutbox.lease_until < now))).values(status="failed", encrypted_token="", error="Email action expired or exhausted its delivery attempts."))
        db.commit()
        # Conditional UPDATE with RETURNING makes claims atomic on PostgreSQL
        # and SQLite. Another worker cannot steal an unexpired lease.
        eligible = (EmailOutbox.available_at <= now) & (EmailOutbox.expires_at > now) & (EmailOutbox.attempts < 3) & or_(EmailOutbox.status == "queued", (EmailOutbox.status == "sending") & (EmailOutbox.lease_until < now))
        candidate = db.scalar(select(EmailOutbox.id).where(eligible).order_by(EmailOutbox.available_at).limit(1))
        if not candidate:
            return False
        claimed = db.scalar(update(EmailOutbox).where(EmailOutbox.id == candidate, eligible).values(status="sending", lease_id=lease_id, lease_until=now + timedelta(minutes=2), attempts=EmailOutbox.attempts + 1).returning(EmailOutbox.id))
        db.commit()
        if not claimed:
            return False
        item = db.get(EmailOutbox, claimed)
        account = db.get(Account, item.account_id)
        encrypted = item.encrypted_token
        purpose = item.purpose
        email = account.email
        account_active = account.status == "active"
    error = ""
    obsolete = False
    try:
        token = cipher().decrypt(encrypted.encode()).decode()
        with SessionLocal() as db:
            if purpose == "teacher_invite":
                from institution_models import TeacherInvitation
                action = db.get(TeacherInvitation, digest(token))
            else:
                action = db.get(AccountAction, digest(token))
            obsolete = not account_active or action is None or action.account_id != item.account_id or getattr(action, "purpose", purpose) != purpose
            if action:
                from accounts import utc
                obsolete = obsolete or utc(action.expires_at) <= now_utc()
        if not obsolete:
            send_action(email, purpose, token)
    except Exception:
        # Provider exception text may contain credentials or private recipients.
        error = "Email delivery failed; check SMTP configuration and provider availability."
    with SessionLocal() as db:
        current = db.scalar(select(EmailOutbox).where(EmailOutbox.id == claimed, EmailOutbox.lease_id == lease_id))
        if current:
            current.error = error
            current.status = "failed" if error and current.attempts >= 3 else "queued" if error else "cancelled" if obsolete else "sent"
            current.available_at = now_utc() + timedelta(seconds=30 * (2 ** current.attempts))
            current.lease_until = None
            if current.status in {"sent", "cancelled", "failed"}:
                current.encrypted_token = ""
            db.commit()
    return True


def start_worker():
    from accounts import mail_configured
    if os.getenv("FORMA_EMAIL_WORKER_ENABLED", "true").lower() != "true" or not mail_configured():
        return None
    stop = threading.Event()
    def run():
        while not stop.is_set():
            try:
                worked = deliver_one()
            except Exception:
                worked = False
            stop.wait(0.2 if worked else 5)
    thread = threading.Thread(target=run, name="forma-email-outbox", daemon=True)
    thread.start()
    return stop, thread
