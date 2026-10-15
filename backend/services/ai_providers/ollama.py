"""Local Ollama transport; shared PDF/validation pipeline lives in qwen.py."""
import json
import threading
import time
from urllib.parse import urlsplit
import httpx
from services.processing_diagnostics import set_stage
from .qwen import PageObservations, PageObservation, SYSTEM, interpret_pages

_inference_lock = threading.Lock()


class LocalProviderBusy(TimeoutError):
    pass


class LocalProviderError(ValueError):
    pass


def structured_completion(config, schema, system, context, progress=None, observe=None):
    """Bounded local text reasoning using the same model lock and cleanup policy."""
    if config.name != 'ollama' or config.model != 'qwen3-vl:8b-instruct':
        raise LocalProviderError('Assessment requires local qwen3-vl:8b-instruct.')
    options = config.options
    body = json.dumps(context, ensure_ascii=False)
    # Refuse instead of silently dropping assignment requirements or evidence.
    # Small enough for the configured 8192-token context with output/schema space.
    if len((system + body + json.dumps(schema)).encode('utf8')) > 18000:
        raise LocalProviderError('Assessment context exceeds the local reasoning budget; narrow the rubric or review manually.')
    if progress: progress()
    if not _inference_lock.acquire(blocking=False):
        raise LocalProviderBusy('A local inference is already active.')
    try:
        with httpx.Client(base_url=local_base_url(options['base_url']), trust_env=False,
                          follow_redirects=False, timeout=httpx.Timeout(min(options['timeout'], 120), connect=5)) as client:
            active = client.get('/api/ps'); active.raise_for_status()
            if any(m.get('name') != config.model for m in active.json().get('models', [])):
                raise LocalProviderBusy('Another local model is loaded; unload it before assessment.')
            shown = client.post('/api/show', json={'model': config.model}); shown.raise_for_status()
            if 'vision' not in shown.json().get('capabilities', []):
                raise LocalProviderError('The local vision model is unavailable.')
            try:
                response = client.post('/api/chat', json={'model': config.model, 'stream': False, 'keep_alive': '1m',
                    'format': schema, 'options': {'temperature': 0, 'num_ctx': 8192, 'num_predict': min(options['output_tokens'], 4096)},
                    'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': body}]})
                response.raise_for_status(); data = response.json()
                if observe: observe(data)  # Only explicit synthetic benchmarks supply this.
                if not data.get('done') or data.get('done_reason') == 'length':
                    raise LocalProviderError('Assessment output is incomplete; manual review required.')
                return data
            finally:
                try: client.post('/api/generate', json={'model': config.model, 'keep_alive': 0}, timeout=10).raise_for_status()
                except httpx.HTTPError: pass
    finally:
        _inference_lock.release()


def local_base_url(value):
    url = urlsplit(value)
    if (url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost', '::1'}
            or url.username or url.password or url.path not in {'', '/'} or url.query or url.fragment):
        raise LocalProviderError('Ollama must use a loopback HTTP address without credentials or path.')
    return value.rstrip('/')


class OllamaProvider:
    def interpret(self, request, progress=None, observe=None):
        options = request.config.options
        base = local_base_url(options['base_url'])
        model = request.config.model
        if 'cloud' in model.lower():
            raise LocalProviderError('Cloud model tags are disabled for local document analysis.')
        if not _inference_lock.acquire(blocking=False):
            raise LocalProviderBusy('A local inference is already active.')
        started = time.monotonic()
        try:
            with httpx.Client(base_url=base, trust_env=False, follow_redirects=False,
                              timeout=httpx.Timeout(options['timeout'], connect=5)) as client:
                return self._interpret(client, request, progress, observe, started)
        finally:
            _inference_lock.release()

    def _interpret(self, client, request, progress, observe, started):
        options = request.config.options
        set_stage('ollama_preflight')
        active = client.get('/api/ps'); active.raise_for_status()
        if any(item.get('name') != request.config.model for item in active.json().get('models', [])):
            raise LocalProviderBusy('Another local model is loaded; unload it before analysis.')
        # This checks a local model already pulled by the operator. Never pull,
        # expose a server, or switch to a paid service from application code.
        shown = client.post('/api/show', json={'model': request.config.model}); shown.raise_for_status()
        if 'vision' not in shown.json().get('capabilities', []):
            raise LocalProviderError('The configured local model does not advertise vision support.')
        def chat(images, context, timeout):
            response = client.post('/api/chat', json={'model': request.config.model, 'stream': False, 'keep_alive': '1m',
                'format': PageObservations.model_json_schema(),
                'options': {'temperature': 0, 'num_ctx': options['context'], 'num_predict': options['output_tokens']},
                'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': json.dumps(context, ensure_ascii=False), 'images': images}]}, timeout=timeout)
            response.raise_for_status()
            return response.json()
        try:
            return interpret_pages(request, chat, progress, observe, started)
        finally:
            try: client.post('/api/generate', json={'model': request.config.model, 'keep_alive': 0}, timeout=10).raise_for_status()
            except httpx.HTTPError: pass  # One-minute keep-alive expiry remains.
