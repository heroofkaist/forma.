"""Mocked cloud transport only. Never uses a real API key or paid request."""
import json
import httpx
import pytest
from sqlalchemy import select
import ai_budget
import document_processing as processing
from budget_models import AIRequestCharge, AIBudgetControl
from processing_models import ProcessingJob, DocumentInterpretation
from test_accounts_courses import platform, identity
from test_document_processing import setup_submission
from test_ai_providers import response_for
from services.ai_providers import engine
from services.ai_providers.openrouter import MODEL

_REAL_CLIENT = httpx.Client


@pytest.fixture
def cloud(monkeypatch):
    settings = {'FORMA_AI_PROVIDER': 'openrouter', 'FORMA_OPENROUTER_MODEL': MODEL,
        'FORMA_OPENROUTER_ENDPOINT': 'synthetic/bf16', 'FORMA_OPENROUTER_API_KEY': 'synthetic-backend-key',
        'FORMA_AI_PAID_ENABLED': 'true', 'FORMA_AI_PAID_FALLBACK_ENABLED': 'false',
        'FORMA_OPENROUTER_PRIVACY_ACKNOWLEDGED': 'true', 'FORMA_AI_MONTHLY_BUDGET_USD': '4',
        'FORMA_AI_MAX_JOB_COST_USD': '0.02', 'FORMA_AI_MAX_CONCURRENT_REQUESTS': '1'}
    for key, value in settings.items(): monkeypatch.setenv(key, value)
    monkeypatch.setattr(engine, 'gemini_interpret', lambda *a, **k: pytest.fail('Paid fallback'))
    return engine.configuration()


def mock_cloud(monkeypatch, factory, calls, mode='success', key_limit=4, endpoint=True):
    real = _REAL_CLIENT
    def respond(request):
        calls.append(request)
        assert request.url.host == 'openrouter.ai'
        assert request.headers['authorization'] == 'Bearer synthetic-backend-key'
        if request.url.path == '/api/v1/key':
            return httpx.Response(200, json={'data': {'limit': key_limit, 'limit_remaining': 4, 'limit_reset': 'monthly', 'is_management_key': False, 'byok_usage_monthly': 0}})
        if request.url.path.endswith('/endpoints'):
            return httpx.Response(200, json={'data': {'endpoints': [{'tag': 'synthetic/bf16', 'provider_name': 'Synthetic',
                'supported_parameters': ['response_format', 'structured_outputs', 'max_tokens'],
                'pricing': {'prompt': '0.00000025', 'completion': '0.00000075'}}] if endpoint else []}})
        assert request.url.path == '/api/v1/chat/completions' and request.method == 'POST'
        # Reservation committed in its own transaction BEFORE network dispatch.
        with factory() as db:
            charge = db.get(AIRequestCharge, request.headers['x-request-id'])
            assert charge.state == 'in_flight' and charge.reserved_nusd <= ai_budget.HARD_JOB
        if mode == 'timeout': raise httpx.ReadTimeout('private prompt student@example.test secret', request=request)
        if mode == '402': return httpx.Response(402, json={'error': {'message': 'private provider body'}})
        if mode == 'bad_http_json': return httpx.Response(200, text='private provider body')
        payload = json.loads(request.content)
        user = payload['messages'][1]['content']
        context = next(c['text'] for c in user if c['type'] == 'text')
        parsed = json.loads(context)
        if 'rubric' in parsed:
            from test_assessment import suggestion
            raw = json.dumps(suggestion(parsed['rubric'], parsed['source']))
            if mode == 'invalid_evidence':
                result = json.loads(raw); result['criteria'][0]['evidence'][0]['quote'] = 'invented passage'; raw = json.dumps(result)
        else:
            raw = response_for({'messages': [{}, {'content': context}]}).json()['message']['content']
        if mode == 'invalid_json': raw = 'private invalid model content'
        if mode == 'invalid_page':
            result = json.loads(raw); result['sections'][0]['page_number'] = 999; raw = json.dumps(result)
        return httpx.Response(200, json={'id': 'gen-' + request.headers['x-request-id'], 'model': MODEL, 'provider': 'Synthetic',
            'usage': {'cost': None if mode == 'no_cost' else 0.0012, 'prompt_tokens': 789, 'completion_tokens': 180},
            'choices': [{'finish_reason': 'stop', 'message': {'content': raw}}]})
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real(**kwargs, transport=httpx.MockTransport(respond)))


def test_cloud_vertical_slice_shared_contract_private_payload_and_review(cloud, platform, monkeypatch):
    client, factory, teacher, student, sid, *_ = setup_submission(platform, monkeypatch)
    calls = []; mock_cloud(monkeypatch, factory, calls)
    path = '/api/document-analysis/' + sid
    queued = client.post(path, headers=teacher, json={}); assert queued.status_code == 202
    assert processing.process_one()
    status = client.get(path + '/status', headers=teacher).json()['jobs'][0]
    assert status['status'] == 'needs_review' and status['provider'] == 'openrouter'
    assert status['usage']['analyzed_pages'] == [1, 2, 3] and not status['partial']
    assert status['usage']['billing'][0]['cost_usd'] == '0.0012'
    payload = json.loads(next(r for r in calls if r.method == 'POST').content)
    assert payload['model'] == MODEL and payload['stream'] is False
    routing = payload['provider']
    assert routing['only'] == ['synthetic/bf16'] and routing['allow_fallbacks'] is False
    assert routing['zdr'] and routing['data_collection'] == 'deny' and routing['require_parameters']
    images = payload['messages'][1]['content'][1:]
    assert len(images) == 3 and all(p['image_url']['url'].startswith('data:image/png;base64,') for p in images)
    serialized = json.dumps(payload)
    assert sid not in serialized and 'student@example.com' not in serialized
    assert 'synthetic-backend-key' not in serialized and 'synthetic.pdf' not in serialized
    original = client.get(path, headers=teacher).json()['items'][0]
    assert original['original']['sections'][0]['latex'] == 'F=ma'
    assert client.get(path, headers=student).status_code == 403
    assert client.get('/academic/student/grades', headers=student).json()['items'] == []
    with factory() as db:
        row = db.scalar(select(AIRequestCharge))
        assert row.model == MODEL and row.actual_nusd == 1_200_000 and row.state == 'settled'
        assert len(row.job_id) == 36


@pytest.mark.parametrize('mode,expected', [('invalid_json', 'failed'), ('invalid_page', 'failed'),
    ('timeout', 'awaiting_budget'), ('bad_http_json', 'awaiting_budget'), ('402', 'awaiting_budget')])
def test_cloud_failures_keep_billing_and_never_retry_blindly(cloud, platform, monkeypatch, caplog, mode, expected):
    client, factory, teacher, student, sid, *_ = setup_submission(platform, monkeypatch)
    calls = []; mock_cloud(monkeypatch, factory, calls, mode=mode)
    path = '/api/document-analysis/' + sid
    job_id = client.post(path, headers=teacher, json={}).json()['id']
    assert processing.process_one() and processing.process_one() is False
    status = client.get(path + '/status', headers=teacher).json()['jobs'][0]
    assert status['status'] == expected and status['attempts'] == 1
    assert client.get(path, headers=teacher).json()['items'] == []
    assert 'private prompt' not in caplog.text and 'private provider body' not in caplog.text
    assert 'private invalid model content' not in caplog.text and 'synthetic-backend-key' not in caplog.text
    with factory() as db:
        charge = db.scalar(select(AIRequestCharge))
        assert charge.job_id == job_id
        assert charge.state == ('settled' if expected == 'failed' else 'unknown')
        if expected == 'failed': assert charge.actual_nusd == 1_200_000
        else: assert charge.reserved_nusd == ai_budget.HARD_JOB and charge.actual_nusd is None
        if mode == '402': assert db.get(AIBudgetControl, 'openrouter').blocked
    if expected == 'awaiting_budget':
        count = len(calls)
        assert client.post(path + '/resume', headers=student, json={}).status_code == 403
        assert client.post(path + '/resume', headers=teacher, json={}).status_code == 409
        assert len(calls) == count  # No network loop on a budget-denied resume.
    if mode == '402':
        # Even a NEW reanalysis cannot keep polling the paused provider.
        assert client.post(path, headers=teacher, json={'reanalyze': True}).status_code == 202
        count = len(calls); assert processing.process_one()
        assert len(calls) == count


@pytest.mark.parametrize('policy', ['disabled', 'privacy', 'key_limit', 'endpoint', 'model'])
def test_cloud_preflight_fails_closed_before_document_transmission(cloud, platform, monkeypatch, policy):
    client, factory, teacher, student, sid, *_ = setup_submission(platform, monkeypatch)
    calls = []; mock_cloud(monkeypatch, factory, calls, key_limit=10 if policy == 'key_limit' else 4, endpoint=policy != 'endpoint')
    if policy == 'model':
        monkeypatch.setenv('FORMA_OPENROUTER_MODEL', 'some/more-expensive-model')
        with pytest.raises(ValueError): engine.configuration()
        assert not calls; return
    if policy == 'disabled': monkeypatch.setenv('FORMA_AI_PAID_ENABLED', 'false')
    if policy == 'privacy': monkeypatch.setenv('FORMA_OPENROUTER_PRIVACY_ACKNOWLEDGED', 'false')
    client.post('/api/document-analysis/' + sid, headers=teacher, json={})
    assert processing.process_one()
    assert not any(r.method == 'POST' for r in calls)
    with factory() as db: assert db.scalar(select(AIRequestCharge)) is None


def test_resume_after_verified_receipt_preserves_job_attempts_and_authorization(cloud, platform, monkeypatch):
    client, factory, teacher, student, sid, *_ = setup_submission(platform, monkeypatch)
    calls = []; mock_cloud(monkeypatch, factory, calls, mode='timeout')
    path = '/api/document-analysis/' + sid
    job_id = client.post(path, headers=teacher, json={}).json()['id']
    assert processing.process_one()
    # Test-only trusted billing receipt; the public API has no cost/refund input.
    with factory() as db: charge_id = db.scalar(select(AIRequestCharge.id))
    ai_budget.record(charge_id, cost='0.0012')
    outsider = identity(client, platform[2], 'unrelated@example.test')
    assert client.post(path + '/resume', headers=outsider, json={}).status_code == 403
    assert client.post(path + '/resume', headers=student, json={}).status_code == 403
    resumed = client.post(path + '/resume', headers=teacher, json={})
    assert resumed.status_code == 202 and resumed.json()['id'] == job_id
    assert resumed.json()['attempts'] == 1
    assert client.post(path + '/resume', headers=teacher, json={}).status_code == 409
    mock_cloud(monkeypatch, factory, calls)
    assert processing.process_one()
    assert client.get(path + '/status', headers=teacher).json()['jobs'][0]['status'] == 'needs_review'
    with factory() as db:
        assert db.get(ProcessingJob, job_id).attempts == 2
        assert len(db.scalars(select(AIRequestCharge)).all()) == 2
        assert len(db.scalars(select(DocumentInterpretation)).all()) == 1


@pytest.mark.parametrize('mode,expected', [('success', 'needs_review'), ('invalid_evidence', 'failed'),
    ('invalid_json', 'failed'), ('timeout', 'awaiting_budget'), ('no_cost', 'needs_review')])
def test_cloud_assessment_full_workflow_shared_ledger(cloud, platform, monkeypatch, mode, expected):
    client, factory, teacher, student, sid, spec, calls = cloud_assessment_fixture(platform, monkeypatch)
    from assessment_models import AssessmentSuggestion
    from persistence import AcademicGrade
    mock_cloud(monkeypatch, factory, calls, mode=mode)
    path = '/api/assessment/' + sid
    assert client.post(path, headers=student, json={}).status_code == 403
    queued = client.post(path, headers=teacher, json={}); assert queued.status_code == 202, queued.text
    job_id = queued.json()['id']
    # Changing deployment settings cannot change a queued job's provider/endpoint.
    monkeypatch.setenv('FORMA_ASSESSMENT_PROVIDER', 'ollama')
    monkeypatch.setenv('FORMA_OPENROUTER_ENDPOINT', 'unapproved/endpoint')
    assert processing.process_one()
    assert processing.process_one() is False
    with factory() as db:
        job = db.get(ProcessingJob, job_id)
        assert job.status == expected and job.context['ai']['name'] == 'openrouter'
        charges = db.scalars(select(AIRequestCharge)).all()
        assert len(charges) == 2 and {c.provider for c in charges} == {'openrouter'}
        assert {c.model for c in charges} == {MODEL}
        charge = next(c for c in charges if c.job_id == job_id)
        assert charge.reserved_nusd == ai_budget.HARD_JOB
        assert charge.state == ('unknown' if mode in {'timeout', 'no_cost'} else 'settled')
        if charge.state == 'settled': assert charge.actual_nusd == 1_200_000
        assert db.scalar(select(AcademicGrade)) is None
        if expected == 'needs_review':
            assert job.usage['provider'] == 'openrouter'
            assert job.usage['billing'][0]['reservation_id'] == charge.id
            assert db.scalar(select(AssessmentSuggestion)).job_id == job_id
    payload = json.loads([r for r in calls if r.method == 'POST'][-1].content)
    assert payload['provider']['only'] == ['synthetic/bf16']
    assert payload['provider']['allow_fallbacks'] is False
    schema = payload['response_format']['json_schema']['schema']
    assert schema['additionalProperties'] is False
    assert all('default' not in json.dumps(v) for v in [schema])
    if mode == 'success':
        item = client.get(path, headers=teacher).json()['items'][0]
        decisions = [dict(question_id=c['question_id'], criterion_id=c['criterion_id'], action='accepted',
            points=2, feedback='Synthetic teacher decision', finding='concern') for c in spec['criteria']]
        response = client.post(path + '/decisions', headers=teacher, json={'suggestion_id': item['id'], 'decisions': decisions})
        assert response.status_code == 201 and response.json()['published'] is False
    assert client.get('/academic/student/grades', headers=student).json()['items'] == []


def test_assessment_provider_selection_is_explicit(cloud, monkeypatch):
    monkeypatch.delenv('FORMA_ASSESSMENT_PROVIDER', raising=False)
    assert engine.assessment_configuration().name == 'ollama'
    monkeypatch.setenv('FORMA_ASSESSMENT_PROVIDER', 'gemini')
    with pytest.raises(ValueError): engine.assessment_configuration()


def cloud_assessment_fixture(platform, monkeypatch):
    import assessment_api
    client, factory, teacher, student, sid, _, assignment, *_ = setup_submission(platform, monkeypatch)
    monkeypatch.setattr(assessment_api, 'SessionLocal', factory)
    monkeypatch.setenv('FORMA_ASSESSMENT_PROVIDER', 'openrouter')
    calls = []; mock_cloud(monkeypatch, factory, calls)
    assert client.post('/api/document-analysis/' + sid, headers=teacher, json={}).status_code == 202
    assert processing.process_one()
    rubric_path = '/api/assessment-rubrics/' + assignment['id']
    spec = client.get(rubric_path, headers=teacher).json()['candidate']
    spec['instructions'] = 'Calculate force and explain reasoning, showing equations and units.'
    for c in spec['criteria']: c['description'] = 'Explain the calculation and units.'
    assert client.post(rubric_path, headers=teacher, json=spec).status_code == 201
    return client, factory, teacher, student, sid, spec, calls


@pytest.mark.parametrize('policy', ['disabled', 'privacy', 'monthly', 'job', 'concurrent'])
def test_assessment_cloud_admission_denies_before_paid_post(cloud, platform, monkeypatch, policy):
    client, factory, teacher, _, sid, _, calls = cloud_assessment_fixture(platform, monkeypatch)
    if policy == 'disabled': monkeypatch.setenv('FORMA_AI_PAID_ENABLED', 'false')
    if policy == 'privacy': monkeypatch.setenv('FORMA_OPENROUTER_PRIVACY_ACKNOWLEDGED', 'false')
    if policy == 'monthly': monkeypatch.setenv('FORMA_AI_MONTHLY_BUDGET_USD', '0.02')
    if policy == 'job': monkeypatch.setenv('FORMA_AI_MAX_JOB_COST_USD', '0.000001')
    if policy == 'concurrent':
        with factory() as db: existing = db.scalar(select(AIRequestCharge)).job_id
        ai_budget.reserve(existing, 'openrouter', MODEL, 1)
    count = sum(r.method == 'POST' for r in calls)
    queued = client.post('/api/assessment/' + sid, headers=teacher, json={})
    assert queued.status_code == 202
    assert processing.process_one() and processing.process_one() is False
    assert sum(r.method == 'POST' for r in calls) == count
    with factory() as db:
        assert db.get(ProcessingJob, queued.json()['id']).status in {'failed', 'awaiting_budget'}
        assert db.scalar(select(AIRequestCharge).where(AIRequestCharge.job_id == queued.json()['id'])) is None
