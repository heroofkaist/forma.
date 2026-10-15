"""Sanitized worker failure evidence without live storage/model/database calls."""
import json
from datetime import timedelta
from types import SimpleNamespace
import pytest
from sqlalchemy import select, func, event
from sqlalchemy.exc import OperationalError
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError
from google.genai.errors import ClientError as GeminiClientError
from test_accounts_courses import platform
from test_document_processing import setup_submission
import document_processing as processing
from processing_models import ProcessingJob, DocumentInterpretation
from persistence import AcademicSubmission, now_utc
from services import document_understanding as understanding
from services.processing_diagnostics import set_stage, log_failure

PRIVATE = 'private-pdf-student@example.com-secret-https://signed.example/key?token=credential'


def entries(caplog):
    return [json.loads(record.message) for record in caplog.records if record.name == 'forma.document_processing']


@pytest.mark.parametrize('failure,stage,retryable', [
    ('missing', 'source_read', False), ('slowdown', 'source_read', True),
    ('denied', 'source_read', False), ('hash', 'source_hash', False),
    ('provider', 'gemini_request', False), ('json', 'response_decode', False),
    ('schema', 'response_validate', False), ('persist', 'analysis_persist', False),
])
def test_failure_diagnostics_and_job_fencing(platform, monkeypatch, caplog, failure, stage, retryable):
    client, factory, teacher, student, sid, structure, assignment, content = setup_submission(platform, monkeypatch)
    path = '/api/document-analysis/' + sid
    job_id = client.post(path, headers=teacher, json={}).json()['id']
    with factory() as db:
        original_path = db.get(AcademicSubmission, sid).file_path
    if failure in {'missing', 'slowdown', 'denied'}:
        def read(_):
            if failure == 'missing': raise FileNotFoundError(PRIVATE)
            raise ClientError({'Error': {'Code': 'SlowDown' if retryable else 'AccessDenied', 'Message': PRIVATE}, 'ResponseMetadata': {'HTTPStatusCode': 503 if retryable else 403}}, 'GetObject')
        monkeypatch.setattr(processing, 'read_blob', read)
    elif failure == 'hash':
        monkeypatch.setattr(processing, 'read_blob', lambda _: b'changed synthetic content')
    elif failure in {'provider', 'json', 'schema'}:
        monkeypatch.setattr(__import__('ai_budget'), 'guard_gemini', lambda: None)  # Offline transport only.
        monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-key')
        class FakeClient:
            def __init__(self, **kwargs): self.models = self
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def generate_content(self, **kwargs):
                if failure == 'provider': raise GeminiClientError(403, {'error': {'message': PRIVATE}})
                return SimpleNamespace(text=PRIVATE if failure == 'json' else json.dumps({'document_type': 'problem_set', 'sections': [{'id': PRIVATE}]}))
        monkeypatch.setattr(understanding.genai, 'Client', FakeClient)
    elif failure == 'persist':
        engine = factory.kw['bind']
        def fail_insert(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith('INSERT INTO document_interpretations'):
                raise ValueError(PRIVATE)
        event.listen(engine, 'before_cursor_execute', fail_insert)
        monkeypatch.setattr(processing, 'interpret_document', lambda *args, **kwargs: ({}, {'ai_called': False}))
    try:
        assert processing.process_one()
    finally:
        if failure == 'persist': event.remove(engine, 'before_cursor_execute', fail_insert)
    log = entries(caplog)[-1]
    assert log['stage'] == stage and log['job_id'] == job_id
    assert log['exception_type'] and log['sanitized_traceback'][0]['frames']
    assert log['retryable'] is retryable
    assert PRIVATE not in caplog.text and 'synthetic-key' not in caplog.text
    assert all(not record.exc_info for record in caplog.records if record.name == 'forma.document_processing')
    with factory() as db:
        assert db.get(AcademicSubmission, sid).file_path == original_path
        assert db.scalar(select(func.count()).select_from(DocumentInterpretation)) == 0
        job = db.get(ProcessingJob, job_id)
        assert job.status == ('queued' if retryable else 'failed')
    if failure == 'slowdown':
        # Same job retries successfully, with no additional submission/analysis.
        monkeypatch.setattr(processing, 'read_blob', lambda _: content)
        with factory() as db:
            db.get(ProcessingJob, job_id).available_at = now_utc() - timedelta(seconds=1); db.commit()
        assert processing.process_one()
        with factory() as db:
            assert db.get(ProcessingJob, job_id).status == 'needs_review'
            assert db.scalar(select(func.count()).select_from(AcademicSubmission)) == 1
            assert db.scalar(select(func.count()).select_from(DocumentInterpretation)) == 1


def test_claim_failure_logs_without_losing_job_or_private_sql(monkeypatch, caplog):
    def fail(): raise RuntimeError(PRIVATE)
    monkeypatch.setattr(processing, 'claim', fail)
    assert processing.process_one() is False
    assert entries(caplog)[0]['stage'] == 'claim'
    assert entries(caplog)[0]['job_id'] is None  # No job claimed yet.
    assert PRIVATE not in caplog.text


def test_failure_state_write_logs_both_exceptions_and_leaves_recoverable_lease(platform, monkeypatch, caplog):
    client, factory, teacher, student, sid, *_ = setup_submission(platform, monkeypatch)
    job_id = client.post('/api/document-analysis/' + sid, headers=teacher, json={}).json()['id']
    def fail(*args, **kwargs):
        # Simulate DB becoming unavailable after source read failed.
        monkeypatch.setattr(processing, 'SessionLocal', lambda: (_ for _ in ()).throw(ConnectionError(PRIVATE)))
        raise FileNotFoundError(PRIVATE)
    monkeypatch.setattr(processing, 'read_blob', fail)
    assert processing.process_one()
    logs = entries(caplog)
    assert [entry['stage'] for entry in logs] == ['source_read', 'failure_persist']
    assert all(entry['job_id'] == job_id for entry in logs)
    assert PRIVATE not in caplog.text
    with factory() as db:
        job = db.get(ProcessingJob, job_id)
        assert job.status == 'extracting' and job.lease_until is not None


def test_storage_and_database_retry_classification():
    assert processing.retryable_error(EndpointConnectionError(endpoint_url=PRIVATE))
    assert processing.retryable_error(ReadTimeoutError(endpoint_url=PRIVATE))
    orig = RuntimeError(PRIVATE); orig.sqlstate = '08006'
    error = OperationalError('private SQL', {'secret': PRIVATE}, orig)
    assert processing.retryable_error(error)
    orig.sqlstate = '42703'  # Undefined column: needs a schema fix, not retries.
    assert not processing.retryable_error(error)


def test_diagnostic_exception_chain_and_sql_parameters_are_never_formatted(caplog):
    set_stage('analysis_persist')
    try:
        try: raise ValueError(PRIVATE)
        except ValueError as original:
            original.sqlstate = '22001'
            raise OperationalError('INSERT secret SQL', {'source': PRIVATE}, original) from original
    except OperationalError as error:
        log_failure(error, job_id='synthetic-job')
    log = entries(caplog)[0]
    assert log['sqlstate'] == '22001' and len(log['sanitized_traceback']) == 2
    assert PRIVATE not in caplog.text and 'INSERT secret SQL' not in caplog.text


def test_outer_worker_exception_is_logged_and_thread_remains_stoppable(monkeypatch, caplog):
    import threading
    import services.processing_diagnostics as diagnostics
    logged = threading.Event()
    original = diagnostics.log_failure
    def capture(error, **kwargs):
        original(error, **kwargs); logged.set()
    def fail(): raise RuntimeError(PRIVATE)
    monkeypatch.setenv('FORMA_DOCUMENT_WORKER_ENABLED', 'true')
    monkeypatch.setattr(processing, 'process_one', fail)
    monkeypatch.setattr(processing, 'log_failure', capture)
    stop, thread = processing.start_worker()
    try:
        assert logged.wait(2)
    finally:
        stop.set(); thread.join(timeout=2)
    assert not thread.is_alive()
    assert entries(caplog)[0]['stage'] == 'worker_loop'
    assert PRIVATE not in caplog.text


def test_real_gemini_sdk_schema_and_request_path_offline(platform, monkeypatch):
    """Exercise SDK conversion/parse with a fake HTTP transport, not a fake SDK."""
    import httpx
    client, factory, teacher, student, sid, structure, assignment, content = setup_submission(platform, monkeypatch)
    expected = understanding.deterministic_interpretation(structure, assignment['questions'], 'problem_set')
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={'candidates': [{'content': {'role': 'model', 'parts': [{'text': json.dumps(expected)}]}, 'finishReason': 'STOP'}], 'usageMetadata': {'promptTokenCount': 123, 'candidatesTokenCount': 56}})
    original = understanding.genai.Client
    def offline_client(**kwargs):
        kwargs['http_options'].httpx_client = httpx.Client(transport=httpx.MockTransport(respond))
        return original(**kwargs)
    monkeypatch.setattr(understanding.genai, 'Client', offline_client)
    monkeypatch.setattr(__import__('ai_budget'), 'guard_gemini', lambda: None)  # Offline SDK only.
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-test-key')
    job = client.post('/api/document-analysis/' + sid, headers=teacher, json={}).json()
    assert processing.process_one()
    assert len(requests) == 1 and requests[0]['generationConfig']['responseMimeType'] == 'application/json'
    with factory() as db:
        row = db.get(ProcessingJob, job['id'])
        assert row.status == 'needs_review' and row.usage['input_tokens'] == 123


def test_explicit_retry_preserves_failed_history_and_original_submission(platform, monkeypatch):
    client, factory, teacher, student, sid, structure, assignment, content = setup_submission(platform, monkeypatch)
    path = '/api/document-analysis/' + sid
    old_id = client.post(path, headers=teacher, json={}).json()['id']
    real_interpret = processing.interpret_document
    monkeypatch.setattr(processing, 'interpret_document', lambda *args, **kwargs: (_ for _ in ()).throw(ValueError(PRIVATE)))
    assert processing.process_one()
    monkeypatch.setattr(processing, 'interpret_document', real_interpret)
    retried = client.post(path, headers=teacher, json={'reanalyze': True})
    assert retried.status_code == 202 and retried.json()['id'] != old_id
    # Repeated retry requests converge on the active job; student has no retry authority.
    assert client.post(path, headers=teacher, json={'reanalyze': True}).json()['id'] == retried.json()['id']
    assert client.post(path, headers=student, json={'reanalyze': True}).status_code == 403
    assert processing.process_one()
    with factory() as db:
        assert db.get(ProcessingJob, old_id).status == 'failed'
        assert db.get(ProcessingJob, retried.json()['id']).status == 'needs_review'
        assert db.scalar(select(func.count()).select_from(AcademicSubmission)) == 1
        assert db.scalar(select(func.count()).select_from(ProcessingJob)) == 2
        assert processing.read_blob(db.get(AcademicSubmission, sid).file_path) == content


def test_non_collision_cache_integrity_failure_is_not_silenced(platform, monkeypatch, caplog):
    from sqlalchemy.exc import IntegrityError
    client, factory, teacher, student, sid, structure, assignment, content = setup_submission(platform, monkeypatch)
    path = '/api/document-analysis/' + sid
    job_id = client.post(path, headers=teacher, json={}).json()['id']
    monkeypatch.setattr(processing, 'interpret_document', lambda *args, **kwargs: ({}, {'ai_called': True}))
    engine = factory.kw['bind']
    def fail_cache(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO document_interpretation_cache'):
            raise IntegrityError(statement, parameters, RuntimeError(PRIVATE))
    event.listen(engine, 'before_cursor_execute', fail_cache)
    try:
        assert processing.process_one()
    finally:
        event.remove(engine, 'before_cursor_execute', fail_cache)
    assert entries(caplog)[0]['exception_type'] == 'IntegrityError'
    assert entries(caplog)[0]['stage'] == 'analysis_persist'
    assert PRIVATE not in caplog.text
    with factory() as db:
        assert db.get(ProcessingJob, job_id).status == 'failed'
        assert db.scalar(select(func.count()).select_from(DocumentInterpretation)) == 0
