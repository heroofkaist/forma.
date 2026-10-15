"""Approval/configuration guards and the one-request operator procedure, mocked only."""
import json
import pytest
from sqlalchemy import select, func
from test_accounts_courses import platform
from test_document_processing import setup_submission
from test_openrouter import cloud, mock_cloud
from scripts import smoke_cloud_qwen as smoke


@pytest.mark.parametrize('url', ['', 'sqlite:///local.db', 'postgresql://db.example/forma_cloud_pilot',
    'postgresql://localhost/production', 'postgresql://localhost/forma_cloud_pilot?host=remote'])
def test_smoke_rejects_nonlocal_or_wrong_database(monkeypatch, url):
    monkeypatch.setenv('FORMA_DATABASE_URL', url)
    with pytest.raises(ValueError): smoke.configure()


def test_smoke_requires_explicit_approval_before_configuration(monkeypatch):
    monkeypatch.setattr('sys.argv', ['smoke_cloud_qwen.py'])
    monkeypatch.setattr(smoke, 'run', lambda: pytest.fail('No approval'))
    with pytest.raises(SystemExit) as error: smoke.main()
    assert error.value.code == 2


def test_one_request_smoke_procedure_and_receipt(cloud, platform, monkeypatch, capsys):
    import persistence
    import httpx
    from test_openrouter import _REAL_CLIENT
    from budget_models import AIRequestCharge
    from assessment_models import AssessmentSuggestion
    from persistence import AcademicGrade
    _, factory, *_ = setup_submission(platform, monkeypatch)
    monkeypatch.setenv('FORMA_ASSESSMENT_PROVIDER', 'openrouter')
    monkeypatch.setattr(smoke, 'configure', lambda: None)
    monkeypatch.setattr(persistence, 'engine', factory.kw['bind'])
    monkeypatch.setattr(persistence, 'SessionLocal', factory)
    monkeypatch.setattr(persistence, 'init_db', lambda: None)
    # Synthetic PDF output stays within pytest's isolated storage.
    monkeypatch.setenv('FORMA_STORAGE_DIR', str(persistence.STORAGE_DIR))
    calls = []; mock_cloud(monkeypatch, factory, calls)
    mock_client = httpx.Client
    def client(**kwargs):
        if kwargs.get('timeout') != 15: return mock_client(**kwargs)
        def receipt(request):
            calls.append(request)
            assert request.method == 'GET' and request.url.path.endswith('/generation')
            generation = request.url.params['id']
            return httpx.Response(200, json={'data': {'id': generation, 'model': cloud.model,
                'is_byok': False, 'total_cost': '0.0013', 'created_at': '2026-10-15T00:00:00Z',
                'tokens_prompt': 789, 'tokens_completion': 180}})
        return _REAL_CLIENT(**kwargs, transport=httpx.MockTransport(receipt))
    monkeypatch.setattr(httpx, 'Client', client)
    smoke.run()
    report = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert report['billing']['cost_usd'] == '0.0013' and report['published'] is False
    assert sum(r.method == 'POST' for r in calls) == 1
    with factory() as db:
        charge = db.scalar(select(AIRequestCharge))
        assert charge.actual_nusd == 1_300_000 and charge.state == 'settled'
        assert db.scalar(select(func.count()).select_from(AssessmentSuggestion)) == 1
        assert db.scalar(select(func.count()).select_from(AcademicGrade)) == 0
