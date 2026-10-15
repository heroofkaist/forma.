"""Atomic reservations and conservative billing; every ambiguous call stays held."""
import os
import re
from datetime import timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from sqlalchemy import select, update, text
from persistence import SessionLocal, now_utc
from budget_models import AIBudgetPeriod, AIBudgetControl, AIRequestCharge

NUSD = Decimal(1_000_000_000)
HARD_MONTH = 4_000_000_000
HARD_JOB = 20_000_000


class BudgetUnavailable(RuntimeError):
    """A safe public reason; no provider bodies/documents may enter this message."""


def money(value):
    if isinstance(value, bool) or value is None or len(str(value)) > 64:
        raise ValueError('Invalid USD amount.')
    try: amount = Decimal(str(value))
    except InvalidOperation as error: raise ValueError('Invalid USD amount.') from error
    if not amount.is_finite() or amount < 0 or amount > Decimal('1000000'):
        raise ValueError('Invalid USD amount.')
    return amount, int((amount * NUSD).to_integral_value(rounding=ROUND_CEILING))


def limits():
    monthly = money(os.getenv('FORMA_AI_MONTHLY_BUDGET_USD', '4.00'))[1]
    job = money(os.getenv('FORMA_AI_MAX_JOB_COST_USD', '0.02'))[1]
    return min(monthly, HARD_MONTH), min(job, HARD_JOB)


def month(now):
    return now.replace(tzinfo=timezone.utc).strftime('%Y-%m') if now.tzinfo is None else now.astimezone(timezone.utc).strftime('%Y-%m')


def lock(db):
    if db.bind.dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(62401705)'))
    else:
        # Acquire SQLite's writer lock, including on the first/empty database.
        db.execute(update(AIBudgetControl).values(updated_at=AIBudgetControl.updated_at))


def control(db, provider):
    row = db.get(AIBudgetControl, provider)
    if row is None:
        row = AIBudgetControl(provider=provider); db.add(row); db.flush()
    return row


def exposure(row):
    return row.actual_nusd if row.state == 'settled' else row.reserved_nusd


def paid_enabled():
    if os.getenv('FORMA_AI_PAID_ENABLED', 'false').lower() != 'true':
        raise BudgetUnavailable('Paid AI is disabled. Manual review and local Ollama remain available.')
    if os.getenv('FORMA_AI_PAID_FALLBACK_ENABLED', 'false').lower() != 'false':
        raise BudgetUnavailable('Paid fallback is forbidden by the budget policy.')


def assert_dispatch_allowed(provider='openrouter'):
    paid_enabled()
    with SessionLocal() as db:
        lock(db)
        row = control(db, provider)
        if row.blocked: raise BudgetUnavailable('Paid inference is paused pending verified billing/budget review.')
        db.commit()


def pause_provider():
    with SessionLocal() as db:
        lock(db)
        row = control(db, 'openrouter')
        row.blocked = True
        if row.reason != 'reported_cost_overrun': row.reason = 'provider_402'
        row.updated_at = now_utc(); db.commit()


def reserve(job_id, provider, model, estimated_nusd, timeout=90, now=None, provider_remaining=None):
    """Hold the WHOLE remaining per-job ceiling, not an optimistic image quote."""
    paid_enabled()
    if not job_id: raise BudgetUnavailable('Paid calls require an existing durable job.')
    now = now or now_utc(); period_id = month(now)
    monthly_limit, job_limit = limits()
    with SessionLocal() as db:
        lock(db)
        state = control(db, provider)
        if state.blocked: raise BudgetUnavailable('Paid inference is paused pending verified billing/budget review.')
        period = db.get(AIBudgetPeriod, period_id)
        if period is None:
            period = AIBudgetPeriod(month=period_id, limit_nusd=monthly_limit); db.add(period); db.flush()
        # Never expire away liability. A crashed request merely becomes unknown.
        db.execute(update(AIRequestCharge).where(AIRequestCharge.state == 'in_flight', AIRequestCharge.expires_at <= now).values(state='unknown'))
        rows = db.scalars(select(AIRequestCharge)).all()
        active = sum(r.state == 'in_flight' for r in rows)
        maximum = min(1, max(1, int(os.getenv('FORMA_AI_MAX_CONCURRENT_REQUESTS', '1'))))
        spent = sum(exposure(r) for r in rows if r.state != 'settled' or r.billing_month == period_id or r.billed_month == period_id)
        own = [r for r in rows if r.job_id == job_id]
        if own: job_limit = min(job_limit, *(r.job_limit_nusd for r in own))
        remaining = job_limit - sum(exposure(r) for r in own)
        if remaining <= 0 or estimated_nusd <= 0 or estimated_nusd > remaining:
            raise BudgetUnavailable('This job has no safe remaining AI allowance; reconcile charges or review manually.')
        if active >= maximum:
            raise BudgetUnavailable('Another paid request is reserved. Resume after it settles.')
        if provider_remaining is not None and remaining > provider_remaining:
            raise BudgetUnavailable('Provider monthly credit cannot cover this reservation.')
        if spent + remaining > min(period.limit_nusd, monthly_limit):
            raise BudgetUnavailable('Monthly AI allowance is unavailable; original PDF remains available for manual review.')
        row = AIRequestCharge(job_id=job_id, provider=provider, model=model, billing_month=period_id,
            reserved_nusd=remaining, job_limit_nusd=job_limit, expires_at=now+timedelta(seconds=timeout+60))
        db.add(row); db.flush(); result = row.id; db.commit(); return result


def record(charge_id, *, cost=None, generation_id=None, tokens=None, billed_month=None, blocked_reason=None, now=None):
    """Idempotent reconciliation: unknown receipts NEVER become a free request."""
    now = now or now_utc()
    try:
        amount, units = money(cost)
    except ValueError:
        amount, units = None, None
    with SessionLocal() as db:
        lock(db)
        row = db.get(AIRequestCharge, charge_id)
        if row is None: raise ValueError('Unknown AI reservation.')
        state = control(db, row.provider)
        if blocked_reason and state.reason != 'reported_cost_overrun':
            state.blocked = True; state.reason = blocked_reason; state.updated_at = now
        if row.state != 'settled' or (units is not None and units > row.actual_nusd):
            if isinstance(generation_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,160}', generation_id): row.generation_id = generation_id
            row.state = 'settled' if units is not None else 'unknown'
            row.actual_nusd = units; row.actual_usd = str(amount) if amount is not None else None
            if isinstance(billed_month, str) and re.fullmatch(r'\d{4}-\d{2}', billed_month): row.billed_month = billed_month
            row.settled_at = now if units is not None else None
            for field, key in [('prompt_tokens', 'prompt_tokens'), ('completion_tokens', 'completion_tokens')]:
                value = (tokens if isinstance(tokens, dict) else {}).get(key)
                if type(value) is int and 0 <= value < 10_000_000: setattr(row, field, value)
            if units is not None and units > row.reserved_nusd:
                state.blocked = True; state.reason = 'reported_cost_overrun'; state.updated_at = now
        db.commit()
        return {'reservation_id': row.id, 'cost_usd': row.actual_usd, 'cost_state': row.state,
                'reserved_usd': str(Decimal(row.reserved_nusd)/NUSD), 'overrun': state.reason == 'reported_cost_overrun'}


def can_resume(job_id, provider='openrouter', db=None):
    try:
        paid_enabled()
        monthly, job_limit = limits()
        from contextlib import nullcontext
        with (nullcontext(db) if db is not None else SessionLocal()) as db:
            lock(db)
            state = control(db, provider)
            if state.blocked: return False
            rows = db.scalars(select(AIRequestCharge)).all()
            current = month(now_utc()); period = db.get(AIBudgetPeriod, current)
            spent = sum(exposure(r) for r in rows if r.state != 'settled' or r.billing_month == current or r.billed_month == current)
            own = [r for r in rows if r.job_id == job_id]
            if own: job_limit = min(job_limit, *(r.job_limit_nusd for r in own))
            remaining = job_limit - sum(exposure(r) for r in own)
            return remaining > 0 and spent+remaining <= min(monthly, period.limit_nusd if period else monthly) and not any(r.state == 'in_flight' and r.expires_at.replace(tzinfo=timezone.utc) > now_utc() for r in rows)
    except (BudgetUnavailable, ValueError): return False


def guard_gemini():
    # Keep the implementation available, but never bypass the only accountable
    # cloud adapter. Gemini billing/key controls need their own audited adapter.
    if os.getenv('GEMINI_API_KEY', '').strip():
        raise BudgetUnavailable('Gemini paid inference is paused under the strict budget policy. Select local Ollama or the budgeted Qwen adapter.')


def resume_provider_after_verified_credit(remaining):
    """Operator-only billing reconciliation; never clears an overrun circuit."""
    if remaining <= 0: raise BudgetUnavailable('Provider monthly credit remains unavailable.')
    with SessionLocal() as db:
        lock(db)
        row = control(db, 'openrouter')
        if row.blocked and row.reason != 'provider_402':
            raise BudgetUnavailable('A cost overrun requires a separate billing investigation.')
        row.blocked = False; row.reason = ''; row.updated_at = now_utc(); db.commit()
