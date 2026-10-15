"""Deterministic atomic accounting; all charges and documents are synthetic."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from sqlalchemy import select, inspect
import ai_budget
from budget_models import AIRequestCharge, AIBudgetPeriod, AIBudgetControl
from processing_models import ProcessingJob
from persistence import AcademicSubmission
from migrations import apply_migrations
from test_accounts_courses import platform
from test_document_processing import setup_submission

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


@pytest.fixture
def ledger(platform, monkeypatch):
    client, factory, teacher, student, sid, *_ = setup_submission(platform, monkeypatch)
    monkeypatch.setenv('FORMA_AI_PAID_ENABLED', 'true')
    monkeypatch.setenv('FORMA_AI_PAID_FALLBACK_ENABLED', 'false')
    monkeypatch.setenv('FORMA_AI_MONTHLY_BUDGET_USD', '4')
    monkeypatch.setenv('FORMA_AI_MAX_JOB_COST_USD', '0.02')
    with factory() as db:
        jobs = []
        for i in range(4):
            job = ProcessingJob(submission_id=sid, requested_by='synthetic', input_hash=str(i)*64,
                content_hash='a'*64, model='synthetic', prompt_version='synthetic', context={})
            db.add(job); db.flush(); jobs.append(job.id)
        db.commit()
    return factory, jobs, sid


def reserve(job, **kwargs):
    return ai_budget.reserve(job, 'openrouter', 'qwen/qwen3-vl-8b-instruct', 1_000_000, **kwargs)


def test_concurrent_workers_cannot_reserve_last_monthly_allowance(ledger, monkeypatch):
    factory, jobs, _ = ledger
    # Two *process-independent* database sessions compete, even on an empty ledger.
    monkeypatch.setenv('FORMA_AI_MONTHLY_BUDGET_USD', '0.02')
    def compete(job):
        try: return reserve(job, now=NOW)
        except ai_budget.BudgetUnavailable: return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(compete, jobs[:2]))
    assert sum(value is not None for value in outcomes) == 1
    with factory() as db:
        rows = db.scalars(select(AIRequestCharge)).all()
        assert len(rows) == 1 and rows[0].reserved_nusd == 20_000_000


def test_retries_reconcile_actuals_and_share_one_job_ceiling(ledger):
    factory, jobs, _ = ledger
    first = reserve(jobs[0], now=NOW)
    ai_budget.record(first, cost='0.003', generation_id='gen-synthetic1', tokens={'prompt_tokens': 123}, now=NOW)
    second = reserve(jobs[0], now=NOW)
    with factory() as db: assert db.get(AIRequestCharge, second).reserved_nusd == 17_000_000
    ai_budget.record(second, cost='0.017', now=NOW)
    assert ai_budget.record(first, cost='0')['cost_usd'] == '0.003'  # Cannot refund a settled receipt.
    with pytest.raises(ai_budget.BudgetUnavailable): reserve(jobs[0], now=NOW)


def test_timeouts_and_crashes_hold_allowance_across_month_boundaries(ledger):
    factory, jobs, _ = ledger
    first = reserve(jobs[0], now=NOW)
    # A crash before receipt reconciliation leaves in_flight; expiry is NOT a refund.
    next_month = datetime(2026, 11, 1, tzinfo=timezone.utc)
    with pytest.raises(ai_budget.BudgetUnavailable): reserve(jobs[0], now=next_month)
    ai_budget.record(first)  # Explicit unknown timeout, still full exposure.
    with pytest.raises(ai_budget.BudgetUnavailable): reserve(jobs[0], now=next_month)
    with factory() as db:
        row = db.get(AIRequestCharge, first)
        assert row.state == 'unknown' and row.reserved_nusd == ai_budget.HARD_JOB
        assert row.actual_nusd is None
    # A different job can use only allowance left AFTER the carried liability.
    second = reserve(jobs[1], now=next_month)
    ai_budget.record(second, cost='0.001', now=next_month)


def test_monthly_reset_settled_costs_reset_unknown_holds_do_not(ledger, monkeypatch):
    factory, jobs, _ = ledger
    monkeypatch.setenv('FORMA_AI_MONTHLY_BUDGET_USD', '0.02')
    first = reserve(jobs[0], now=NOW); ai_budget.record(first, cost='0.02', now=NOW)
    with pytest.raises(ai_budget.BudgetUnavailable): reserve(jobs[1], now=NOW)
    november = datetime(2026, 11, 1, tzinfo=timezone.utc)
    second = reserve(jobs[1], now=november); ai_budget.record(second, now=november)
    december = datetime(2026, 12, 1, tzinfo=timezone.utc)
    with pytest.raises(ai_budget.BudgetUnavailable): reserve(jobs[2], now=december)
    with factory() as db:
        assert db.get(AIBudgetPeriod, '2026-10').limit_nusd == 20_000_000
        assert db.get(AIBudgetPeriod, '2026-11').limit_nusd == 20_000_000


def test_global_concurrency_expiry_and_provider_remaining(ledger):
    factory, jobs, _ = ledger
    first = reserve(jobs[0], now=NOW, timeout=1)
    with pytest.raises(ai_budget.BudgetUnavailable): reserve(jobs[1], now=NOW)
    with pytest.raises(ai_budget.BudgetUnavailable): reserve(jobs[1], now=NOW+timedelta(minutes=2), provider_remaining=100)
    second = reserve(jobs[1], now=NOW+timedelta(minutes=2))
    with factory() as db:
        assert db.get(AIRequestCharge, first).state == 'unknown'
        assert db.get(AIRequestCharge, second).state == 'in_flight'


def test_402_pause_and_cost_overrun_cannot_be_cleared_by_teacher_or_clock(ledger):
    factory, jobs, _ = ledger
    first = reserve(jobs[0], now=NOW)
    ai_budget.record(first, blocked_reason='provider_402')
    with pytest.raises(ai_budget.BudgetUnavailable): reserve(jobs[1], now=NOW+timedelta(days=60))
    assert not ai_budget.can_resume(jobs[1])
    with pytest.raises(ai_budget.BudgetUnavailable): ai_budget.resume_provider_after_verified_credit(0)
    ai_budget.resume_provider_after_verified_credit(100_000_000)
    second = reserve(jobs[1], now=NOW+timedelta(days=60))
    receipt = ai_budget.record(second, cost='0.025')
    assert receipt['overrun'] and receipt['cost_usd'] == '0.025'
    with pytest.raises(ai_budget.BudgetUnavailable): ai_budget.resume_provider_after_verified_credit(100_000_000)
    with factory() as db: assert db.get(AIBudgetControl, 'openrouter').reason == 'reported_cost_overrun'


@pytest.mark.parametrize('invalid', [None, True, '-1', 'NaN', 'Infinity', {}, []])
def test_invalid_cost_is_never_a_refund_and_ledger_has_no_document_fields(ledger, invalid):
    factory, jobs, _ = ledger
    charge = reserve(jobs[0], now=NOW)
    receipt = ai_budget.record(charge, cost=invalid, generation_id={'private': 'not a string'}, billed_month=[])
    assert receipt['cost_state'] == 'unknown' and receipt['cost_usd'] is None
    columns = set(AIRequestCharge.__table__.c.keys())
    assert not columns & {'prompt', 'content', 'student_id', 'email', 'api_key', 'image', 'url'}


def test_migration_008_is_additive_idempotent_and_retains_submission(ledger):
    factory, jobs, sid = ledger
    engine = factory.kw['bind']
    with factory() as db:
        before = db.get(AcademicSubmission, sid).file_path
    # Simulate an existing pre-008 database with every original record present.
    from account_models import SchemaMigration
    with engine.begin() as connection:
        for name in ['ai_request_charges', 'ai_budget_controls', 'ai_budget_periods']:
            AIRequestCharge.metadata.tables[name].drop(connection)
        connection.execute(SchemaMigration.__table__.delete().where(SchemaMigration.version == '008_ai_budget_ledger'))
    apply_migrations(engine); apply_migrations(engine)
    assert {'ai_request_charges', 'ai_budget_periods', 'ai_budget_controls'} <= set(inspect(engine).get_table_names())
    charge = reserve(jobs[0], now=NOW)
    apply_migrations(engine)
    with factory() as db:
        assert db.get(AcademicSubmission, sid).file_path == before
        assert db.get(AIRequestCharge, charge)
        assert db.get(ProcessingJob, jobs[0])


def test_limits_are_clamped_and_fractional_costs_round_up(monkeypatch):
    monkeypatch.setenv('FORMA_AI_MONTHLY_BUDGET_USD', '999'); monkeypatch.setenv('FORMA_AI_MAX_JOB_COST_USD', '99')
    assert ai_budget.limits() == (4_000_000_000, 20_000_000)
    assert ai_budget.money('0.00000000001')[1] == 1


def test_billing_metadata_reconciliation_never_requests_generation_content(ledger):
    import httpx
    from scripts.reconcile_ai_billing import reconcile
    from services.ai_providers.openrouter import MODEL
    factory, jobs, _ = ledger
    charge = reserve(jobs[0], now=NOW)
    ai_budget.record(charge, generation_id='gen-synthetic1')  # Missing usage.cost.
    requests = []
    def receipt(request):
        requests.append(request)
        assert request.url.path == '/api/v1/generation' and request.method == 'GET'
        assert request.url.params['id'] == 'gen-synthetic1'
        return httpx.Response(200, json={'data': {'id': 'gen-synthetic1', 'model': MODEL,
            'is_byok': False, 'total_cost': 0.00123, 'created_at': '2026-10-15T00:00:00Z',
            'tokens_prompt': 123, 'tokens_completion': 45}})
    with httpx.Client(base_url='https://openrouter.ai/api/v1', transport=httpx.MockTransport(receipt)) as client:
        assert reconcile(client, charge)['cost_usd'] == '0.00123'
    assert len(requests) == 1
    with factory() as db:
        row = db.get(AIRequestCharge, charge)
        assert row.state == 'settled' and row.billed_month == '2026-10'


def test_paid_gemini_and_legacy_grader_cannot_bypass_ledger(monkeypatch):
    from services.ai_providers.engine import GeminiProvider, DocumentRequest, ProviderConfig
    from services.ai_grader import grade_image, GradingConfigurationError
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-key')
    monkeypatch.setattr(__import__('services.ai_providers.engine', fromlist=['gemini_interpret']), 'gemini_interpret',
                        lambda *a, **k: pytest.fail('Unaccounted Gemini inference'))
    with pytest.raises(ai_budget.BudgetUnavailable):
        GeminiProvider().interpret(DocumentRequest(b'', 'pdf', {}, [], 'problem_set', ProviderConfig('gemini', 'legacy', 'v1', {})))
    with pytest.raises(GradingConfigurationError): grade_image(b'', '', '', '')
