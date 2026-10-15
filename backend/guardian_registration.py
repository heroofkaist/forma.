"""Parent mailbox approval for one browser-bound teen registration, never parental identity verification."""
import os
import re
import secrets
from datetime import timedelta
from urllib.parse import urlsplit
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update, delete, or_
import accounts
import age_screen
from account_models import GuardianRegistration, Account, AccountSession
from email_delivery import cipher
from persistence import now_utc

router = APIRouter(prefix='/api/accounts/guardian-consent', tags=['Guardian registration'])
NOTICE_VERSION = 'teen-registration-2026-10-v1'
NOTICE = ('Разрешаю ребёнку 13–17 лет создать учётную запись Forma. Для работы с курсами и проверки заданий '
          'будут обрабатываться email, отображаемое имя и учебные материалы. Оценки утверждает преподаватель. '
          'Я ознакомился(ась) с уведомлением об обработке данных и знаю, куда обратиться для отзыва согласия.')


def configuration():
    notice = os.getenv('FORMA_GUARDIAN_PRIVACY_NOTICE_URL', '').strip()
    contact = os.getenv('FORMA_GUARDIAN_PRIVACY_CONTACT', '').strip()
    try:
        url = urlsplit(notice)
        safe_notice = (url.scheme == 'https' and bool(url.hostname) and not url.username and not url.password and not url.fragment and not url.query)
    except ValueError:
        safe_notice = False
    enabled = (accounts.registration_enabled() and os.getenv('FORMA_GUARDIAN_REGISTRATION_ENABLED', 'false').lower() == 'true'
               and safe_notice and bool(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', contact)))
    return {'enabled': bool(enabled), 'notice_url': notice if enabled else '', 'privacy_contact': contact if enabled else ''}


def require_enabled():
    config = configuration()
    if not config['enabled']:
        raise HTTPException(503, 'Guardian registration is not configured.')
    return config


def browser_proof(request, token):
    if age_screen.require_proof(token, request.cookies.get(age_screen.COOKIE)) != 'guardian':
        raise HTTPException(403, 'Guardian approval is only available for the teen registration path.')
    return accounts.digest(token)


class GuardianRequest(accounts.EmailPayload):
    age_check_token: str = Field(min_length=20, max_length=200)


class BrowserStatus(BaseModel):
    model_config = ConfigDict(extra='forbid')
    age_check_token: str = Field(min_length=20, max_length=200)


class ParentToken(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(min_length=32, max_length=100)


class ParentDecision(ParentToken):
    decision: str = Field(pattern='^(approve|decline)$')
    adult_guardian: bool = False
    consent: bool = False


def locked(db, **where):
    query = select(GuardianRegistration).filter_by(**where)
    if db.bind.dialect.name == 'sqlite':
        db.execute(update(GuardianRegistration).filter_by(**where).values(status=GuardianRegistration.status))
    return db.scalar(query.with_for_update())


def parent_record(db, token, lock=False):
    row = locked(db, token_hash=accounts.digest(token)) if lock else db.scalar(select(GuardianRegistration).where(GuardianRegistration.token_hash == accounts.digest(token)))
    if not row or accounts.utc(row.expires_at) <= now_utc():
        raise HTTPException(410, 'Guardian link is invalid or expired.')
    return row


@router.post('/request', status_code=202)
def request_consent(payload: GuardianRequest, request: Request):
    config = require_enabled()
    proof = browser_proof(request, payload.age_check_token)
    accounts.rate_limit(request, 'guardian-request', payload.email, 3)
    accounts.rate_limit(request, 'guardian-proof', proof, 5)
    # Serialize requests from this same browser proof; repeated clicks cannot create duplicate mail.
    from account_models import RateBucket
    with accounts.SessionLocal() as db:
        # The age endpoint already creates rate buckets; use a separate transaction admission lock on PostgreSQL.
        if db.bind.dialect.name == 'postgresql':
            db.connection().exec_driver_sql('SELECT pg_advisory_xact_lock(62401712)')
        else:
            db.execute(update(RateBucket).values(count=RateBucket.count))
        existing = db.scalar(select(GuardianRegistration).where(GuardianRegistration.proof_hash == proof))
        if existing:
            if existing.status != 'pending':
                return {'request_code': existing.id[:8].upper(), 'sent': False, 'status': existing.status}
            if accounts.utc(existing.created_at) + timedelta(seconds=60) > now_utc():
                raise HTTPException(429, 'Wait before requesting another guardian email.', headers={'Retry-After':'60'})
            token = secrets.token_urlsafe(32)
            existing.token_hash = accounts.digest(token)
            existing.encrypted_email = cipher().encrypt(payload.email.encode()).decode()
            existing.encrypted_token = cipher().encrypt(token.encode()).decode()
            existing.created_at = now_utc(); existing.expires_at = now_utc()+timedelta(hours=1)
            existing.delivery_status = 'queued'; existing.attempts = 0; existing.available_at = now_utc()
            existing.lease_id = None; existing.lease_until = None
            db.commit()
            return {'request_code': existing.id[:8].upper(), 'sent': True, 'status': 'pending'}
        token = secrets.token_urlsafe(32)
        row = GuardianRegistration(proof_hash=proof, token_hash=accounts.digest(token),
            encrypted_email=cipher().encrypt(payload.email.encode()).decode(),
            encrypted_token=cipher().encrypt(token.encode()).decode(), expires_at=now_utc()+timedelta(hours=1),
            notice_url=config['notice_url'], privacy_contact=config['privacy_contact'], notice_version=NOTICE_VERSION, notice_text=NOTICE)
        db.add(row); db.flush(); code = row.id[:8].upper(); db.commit()
        return {'request_code': code, 'sent': True, 'status': 'pending'}


@router.post('/status')
def consent_status(payload: BrowserStatus, request: Request):
    require_enabled(); proof = browser_proof(request, payload.age_check_token)
    accounts.rate_limit(request, 'guardian-status', proof, 120)
    with accounts.SessionLocal() as db:
        row = db.scalar(select(GuardianRegistration).where(GuardianRegistration.proof_hash == proof))
        status = row.status if row else 'missing'
        if row and status == 'pending' and accounts.utc(row.expires_at) <= now_utc(): status = 'expired'
        return {'status': status, 'request_code': row.id[:8].upper() if row else None}


@router.post('/inspect')
def inspect_consent(payload: ParentToken, request: Request):
    require_enabled(); accounts.rate_limit(request, 'guardian-link', accounts.digest(payload.token), 20)
    with accounts.SessionLocal() as db:
        row = parent_record(db, payload.token)
        return {'status': row.status, 'request_code': row.id[:8].upper(), 'notice': row.notice_text,
                'notice_url': row.notice_url, 'privacy_contact': row.privacy_contact}


@router.post('/decision')
def decide_consent(payload: ParentDecision, request: Request):
    require_enabled(); accounts.rate_limit(request, 'guardian-decision', accounts.digest(payload.token), 10)
    with accounts.SessionLocal() as db:
        row = parent_record(db, payload.token, lock=True)
        if payload.decision == 'approve':
            if not payload.adult_guardian or not payload.consent:
                raise HTTPException(422, 'Guardian attestation and consent are required.')
            if row.status != 'pending': raise HTTPException(409, 'Guardian request has already been decided.')
            row.status = 'approved'; row.approved_at = now_utc()
        else:
            row.status = 'declined'
            if row.account_id:
                db.get(Account, row.account_id).status = 'consent_revoked'
                db.execute(delete(AccountSession).where(AccountSession.account_id == row.account_id))
        row.encrypted_token = ''; db.commit()
        return {'status': row.status}


def permission_for_registration(db, proof_token, email, for_update=True):
    require_enabled()
    row = locked(db, proof_hash=accounts.digest(proof_token)) if for_update else db.scalar(select(GuardianRegistration).where(GuardianRegistration.proof_hash == accounts.digest(proof_token)))
    if (not row or row.status != 'approved' or row.account_id or not row.approved_at or
            accounts.utc(row.approved_at) + timedelta(hours=24) <= now_utc()):
        raise HTTPException(403, 'Guardian approval is required or has expired.')
    parent = cipher().decrypt(row.encrypted_email.encode()).decode()
    if parent.casefold() == email.casefold():
        raise HTTPException(422, 'Use a separate child email address after guardian approval.')
    return row


def deliver_one():
    """Use the existing worker and SMTP transport, with atomic leases and bounded retries."""
    now = now_utc(); lease = str(uuid4())
    with accounts.SessionLocal() as db:
        # Unused requests have no child account and expire after the browser permission window.
        db.execute(delete(GuardianRegistration).where(GuardianRegistration.account_id.is_(None),
            GuardianRegistration.expires_at < now - timedelta(hours=24)))
        db.execute(update(GuardianRegistration).where(GuardianRegistration.delivery_status.in_(['queued','sending']),
            or_(GuardianRegistration.expires_at <= now, GuardianRegistration.status != 'pending',
                (GuardianRegistration.attempts >= 3) & (GuardianRegistration.lease_until < now))).values(delivery_status='cancelled', encrypted_token=''))
        db.commit()
        eligible = ((GuardianRegistration.status == 'pending') & (GuardianRegistration.available_at <= now) &
            (GuardianRegistration.expires_at > now) & (GuardianRegistration.attempts < 3) &
            or_(GuardianRegistration.delivery_status == 'queued', (GuardianRegistration.delivery_status == 'sending') & (GuardianRegistration.lease_until < now)))
        candidate = db.scalar(select(GuardianRegistration.id).where(eligible).order_by(GuardianRegistration.created_at).limit(1))
        if not candidate: return False
        claimed = db.scalar(update(GuardianRegistration).where(GuardianRegistration.id == candidate, eligible).values(
            delivery_status='sending', lease_id=lease, lease_until=now+timedelta(minutes=2), attempts=GuardianRegistration.attempts+1).returning(GuardianRegistration.id))
        db.commit()
        if not claimed: return False
        row = db.get(GuardianRegistration, claimed)
        encrypted_email, encrypted_token = row.encrypted_email, row.encrypted_token
    failed = False
    try:
        require_enabled()
        accounts.send_action(cipher().decrypt(encrypted_email.encode()).decode(), 'guardian_consent', cipher().decrypt(encrypted_token.encode()).decode())
    except Exception:
        failed = True
    with accounts.SessionLocal() as db:
        row = db.scalar(select(GuardianRegistration).where(GuardianRegistration.id == claimed, GuardianRegistration.lease_id == lease))
        if row:
            row.delivery_status = 'failed' if failed and row.attempts >= 3 else 'queued' if failed else 'sent'
            row.available_at = now_utc()+timedelta(seconds=30*(2**row.attempts)); row.lease_until = None
            if row.delivery_status in {'sent','failed'}: row.encrypted_token = ''
            db.commit()
    return True
