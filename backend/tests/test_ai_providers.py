import base64
import io
import json
from dataclasses import replace
import httpx
import pytest
import pymupdf
from PIL import Image
from sqlalchemy import select
from test_accounts_courses import platform
from test_document_processing import setup_submission
from services.ai_providers import engine
from services.ai_providers.ollama import OllamaProvider, LocalProviderError
from services.document_understanding import deterministic_interpretation
import document_processing as processing
from processing_models import ProcessingJob
from services.processing_diagnostics import log_failure, set_stage


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setenv('FORMA_AI_PROVIDER', 'ollama')
    monkeypatch.setenv('FORMA_OLLAMA_MODEL', 'qwen3-vl:8b-instruct')
    monkeypatch.setenv('FORMA_OLLAMA_BASE_URL', 'http://127.0.0.1:11434')
    # A local failure must never invoke the preserved paid adapter.
    monkeypatch.setattr(engine, 'gemini_interpret', lambda *a, **k: pytest.fail('Paid fallback invoked'))
    return engine.configuration()


def test_selection_and_historical_job_identity(local, monkeypatch):
    assert local.name == 'ollama' and local.model == 'qwen3-vl:8b-instruct'
    assert engine.config_for_job({'visual_pages': 8}, 'old-gemini-model', 'old-version').name == 'gemini'
    assert engine.config_for_job({'ai': engine.asdict(local)}, 'unused', 'unused') == local
    monkeypatch.setenv('FORMA_AI_PROVIDER', 'unknown')
    with pytest.raises(ValueError): engine.configuration()


@pytest.mark.parametrize('url', ['https://public.example', 'http://10.0.0.1:11434', 'http://localhost:11434/path', 'http://secret@127.0.0.1:11434', 'http://127.0.0.1:11434?key=secret'])
def test_loopback_only_privacy(local, monkeypatch, url):
    monkeypatch.setenv('FORMA_OLLAMA_BASE_URL', url)
    with pytest.raises(LocalProviderError): engine.configuration()


def mock_ollama(monkeypatch, reply, requests):
    real = httpx.Client
    def handler(request):
        payload = json.loads(request.content) if request.content else {}
        requests.append((request.url.path, payload))
        if request.url.path == '/api/ps': return httpx.Response(200, json={'models': []})
        if request.url.path == '/api/show': return httpx.Response(200, json={'capabilities': ['vision']})
        if request.url.path == '/api/generate': return httpx.Response(200, json={'done': True})
        assert request.url.host == '127.0.0.1' and request.url.path == '/api/chat'
        assert 'authorization' not in request.headers
        return reply(request, payload)
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real(**kwargs, transport=httpx.MockTransport(handler)))


def response_for(payload):
    context = json.loads(payload['messages'][1]['content'])
    pages = [{'number': p['page_number'], 'unit': p['unit'], 'text': p['text']} for p in context['sources']]
    result = deterministic_interpretation({'pages': pages}, context['questions'], context['document_type'])
    for section in result['sections']:
        section['latex'] = 'F=ma'; section['interpretation'] = 'Proposed equation meaning; not observed text.'
    result = {'sections': [{**{k: s[k] for k in ('page_number', 'question_id', 'kind', 'evidence_kind', 'readability', 'latex', 'interpretation', 'uncertainty_notes')}, 'observed_text': s['transcription']} for s in result['sections']], 'warnings': []}
    return httpx.Response(200, json={'done': True, 'done_reason': 'stop', 'message': {'content': json.dumps(result)}, 'prompt_eval_count': 100, 'eval_count': 80})


def test_all_pages_rendered_partial_explicit_and_no_private_metadata(local, monkeypatch, platform):
    client, factory, teacher, student, sid, structure, assignment, content = setup_submission(platform, monkeypatch)
    # setup_submission patches only storage/auth, not the selected local provider.
    requests = []
    mock_ollama(monkeypatch, lambda request, payload: response_for(payload), requests)
    config = replace(local, options={**local.options, 'pages': 2})
    result, usage = engine.interpret_document(content, 'pdf', structure, assignment['questions'], 'problem_set', config)
    chats = [payload for path, payload in requests if path == '/api/chat']
    assert len(chats) == 2 and usage['analyzed_pages'] == [1, 2]
    assert usage['partial'] and usage['omitted_pages'] == [3]
    assert any('PARTIAL ANALYSIS' in warning for warning in result['warnings'])
    for payload in chats:
        assert payload['stream'] is False and payload['options']['num_ctx'] == 8192
        assert len(payload['messages'][1]['images']) == 1
        with Image.open(io.BytesIO(base64.b64decode(payload['messages'][1]['images'][0]))) as img:
            assert max(img.size) <= config.options['image_edge']
        serialized = json.dumps(payload)
        assert 'teacher@example.com' not in serialized and sid not in serialized
        assert 'synthetic.pdf' not in serialized and 'GEMINI_API_KEY' not in serialized
    assert result['sections'][0]['interpretation'] and result['requires_human_review']
    assert requests[-1] == ('/api/generate', {'model': local.model, 'keep_alive': 0})


@pytest.mark.parametrize('failure', ['invalid_json', 'timeout', 'unavailable', 'invalid_page', 'truncated'])
def test_failures_are_strict_local_and_sanitized(local, monkeypatch, platform, caplog, failure):
    client, factory, teacher, student, sid, structure, assignment, content = setup_submission(platform, monkeypatch)
    private = 'synthetic-private-document student@example.test signed-url?key=secret'
    def fail(request, payload):
        if failure == 'timeout': raise httpx.ReadTimeout(private, request=request)
        if failure == 'unavailable': raise httpx.ConnectError(private, request=request)
        if failure == 'invalid_page':
            result = deterministic_interpretation({'pages': [structure['pages'][0]]}, assignment['questions'], 'problem_set')
            result['sections'][0]['page_number'] = 99
            text = json.dumps({'sections': [{'page_number': 99, 'question_id': 'q1', 'kind': 'answer', 'observed_text': 'F=ma', 'evidence_kind': 'visual_page', 'readability': 'readable'}]})
        else: text = private
        return httpx.Response(200, json={'done': True, 'done_reason': 'length' if failure == 'truncated' else 'stop', 'message': {'content': text}})
    requests = []; mock_ollama(monkeypatch, fail, requests)
    with pytest.raises((ValueError, httpx.TransportError)) as raised:
        engine.interpret_document(content, 'pdf', structure, assignment['questions'], 'problem_set', local)
    log_failure(raised.value, job_id='synthetic-job')
    assert private not in caplog.text and 'secret' not in caplog.text
    assert any(path == '/api/chat' for path, _ in requests)
    assert not any('gemini' in payload.get('model', '') for _, payload in requests)


def test_durable_local_job_reaches_existing_teacher_review(local, monkeypatch, platform):
    client, factory, teacher, student, sid, *_ = setup_submission(platform, monkeypatch)
    requests = []; mock_ollama(monkeypatch, lambda request, payload: response_for(payload), requests)
    path = '/api/document-analysis/' + sid
    queued = client.post(path, headers=teacher, json={}); assert queued.status_code == 202
    with factory() as db:
        job = db.get(ProcessingJob, queued.json()['id'])
        assert job.context['ai']['name'] == 'ollama'
    monkeypatch.setenv('FORMA_AI_PROVIDER', 'gemini')  # Queued job keeps its Ollama snapshot.
    assert processing.process_one()
    status = client.get(path + '/status', headers=teacher).json()['jobs'][0]
    assert status['status'] == 'needs_review' and status['provider'] == 'ollama'
    result = client.get(path, headers=teacher).json()['items'][0]['original']
    assert result['sections'][0]['latex'] == 'F=ma'
    assert client.get(path, headers=student).status_code == 403
    assert client.post(path + '/corrections', headers=teacher, json={'interpretation_id': client.get(path, headers=teacher).json()['items'][0]['id'], 'result': result, 'confirmed': True}).status_code == 201
    assert client.get('/academic/student/grades', headers=student).json()['items'] == []


def test_unavailable_local_server_requeues_durable_job_without_paid_fallback(local, monkeypatch, platform, caplog):
    client, factory, teacher, student, sid, *_ = setup_submission(platform, monkeypatch)
    real_client = httpx.Client
    def unavailable(request):
        raise httpx.ConnectError('private content must not be logged', request=request)
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(unavailable)))
    path = '/api/document-analysis/' + sid
    assert client.post(path, headers=teacher, json={}).status_code == 202
    assert processing.process_one()
    status = client.get(path + '/status', headers=teacher).json()['jobs'][0]
    assert status['provider'] == 'ollama' and status['status'] == 'queued' and status['attempts'] == 1
    assert 'private content' not in caplog.text
    assert client.get(path, headers=teacher).json()['items'] == []
