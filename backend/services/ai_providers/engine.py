"""Small provider registry; jobs snapshot provider/config, never fail over."""
import os
import ai_budget
from dataclasses import dataclass, asdict, field
from typing import Callable, Protocol
from services.document_understanding import PROMPT_VERSION, gemini_interpret, limit
from services.ai_grader import configured_model


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    model: str
    version: str
    options: dict


@dataclass(frozen=True)
class DocumentRequest:
    content: bytes
    file_type: str
    structure: dict
    questions: list
    document_type: str
    config: ProviderConfig
    job_id: str | None = None
    assignment_context: dict = field(default_factory=dict)


class Provider(Protocol):
    def interpret(self, request: DocumentRequest, progress: Callable | None = None,
                  observe: Callable | None = None) -> tuple[dict, dict]: ...


class GeminiProvider:
    def interpret(self, request, progress=None, observe=None):
        ai_budget.guard_gemini()
        if progress: progress()
        return gemini_interpret(request.content, request.file_type, request.structure,
                                request.questions, request.document_type, request.config.model,
                                request.config.options['visual_pages'])


def configuration(name=None):
    # Preserve existing deployments until an operator explicitly selects Ollama.
    name = (name or os.getenv('FORMA_AI_PROVIDER', 'gemini')).strip().lower()
    if name == 'gemini':
        return ProviderConfig(name, configured_model(), PROMPT_VERSION,
                              {'visual_pages': limit('FORMA_AI_VISUAL_PAGES', 8, 12)})
    if name == 'openrouter':
        import re
        from .openrouter import MODEL
        model = os.getenv('FORMA_OPENROUTER_MODEL', MODEL)
        endpoint = os.getenv('FORMA_OPENROUTER_ENDPOINT', '')
        if model != MODEL or not re.fullmatch(r'[a-z0-9_-]+/[a-z0-9_.-]+', endpoint):
            raise ValueError('OpenRouter requires the exact Qwen model and one explicit approved endpoint slug.')
        return ProviderConfig(name, model, 'qwen-cloud-v4-readable-feedback', {
            'endpoint': endpoint, 'pages': limit('FORMA_OPENROUTER_MAX_PAGES', 3, 3),
            'batch_pages': limit('FORMA_OPENROUTER_BATCH_PAGES', 3, 3),
            'image_edge': limit('FORMA_OPENROUTER_IMAGE_EDGE', 1120, 1400),
            'output_tokens': limit('FORMA_OPENROUTER_OUTPUT_TOKENS', 2200, 3000),
            'timeout': limit('FORMA_OPENROUTER_TIMEOUT_SECONDS', 60, 90), 'total_seconds': 180,
            'prompt_price_cap': os.getenv('FORMA_OPENROUTER_MAX_PROMPT_USD_PER_MILLION', '0.25'),
            'completion_price_cap': os.getenv('FORMA_OPENROUTER_MAX_COMPLETION_USD_PER_MILLION', '0.75')})
    if name == 'ollama':
        from .ollama import local_base_url
        return ProviderConfig(name, os.getenv('FORMA_OLLAMA_MODEL', 'qwen3-vl:8b-instruct'), 'qwen-document-v4-readable-feedback', {
            'base_url': local_base_url(os.getenv('FORMA_OLLAMA_BASE_URL', 'http://127.0.0.1:11434')),
            'pages': limit('FORMA_OLLAMA_MAX_PAGES', 3, 6),
            'batch_pages': limit('FORMA_OLLAMA_BATCH_PAGES', 1, 2),
            'image_edge': limit('FORMA_OLLAMA_IMAGE_EDGE', 1120, 1400),
            'context': limit('FORMA_OLLAMA_CONTEXT', 8192, 8192),
            'output_tokens': limit('FORMA_OLLAMA_OUTPUT_TOKENS', 2200, 4096),
            'timeout': limit('FORMA_OLLAMA_TIMEOUT_SECONDS', 120, 180),
            'total_seconds': limit('FORMA_OLLAMA_TOTAL_SECONDS', 480, 900),
        })
    raise ValueError('Unsupported FORMA_AI_PROVIDER; choose ollama, openrouter or gemini.')


def config_for_job(context, model, version):
    snapshot = context.get('ai')
    if snapshot:
        return ProviderConfig(**snapshot)
    # Historical jobs remain Gemini jobs, even when local defaults change.
    return ProviderConfig('gemini', model, version, {'visual_pages': context['visual_pages']})


def interpret_document(content, file_type, structure, questions, document_type, config,
                       progress=None, observe=None, job_id=None, assignment_context=None):
    if config.name == 'ollama':
        from .ollama import OllamaProvider
        provider: Provider = OllamaProvider()
    elif config.name == 'openrouter':
        from .openrouter import OpenRouterProvider
        provider = OpenRouterProvider()
    elif config.name == 'gemini':
        provider = GeminiProvider()
    else:
        raise ValueError('Unsupported persisted AI provider.')
    return provider.interpret(DocumentRequest(content, file_type, structure, questions,
                                             document_type, config, job_id, assignment_context or {}), progress, observe)


def assessment_configuration():
    selected = os.getenv('FORMA_AI_PROVIDER', 'ollama').strip().lower()
    name = os.getenv('FORMA_ASSESSMENT_PROVIDER', selected if selected in {'ollama', 'openrouter'} else 'ollama').strip().lower()
    if name not in {'ollama', 'openrouter'}:
        raise ValueError('Assessment requires explicitly selected Ollama or OpenRouter; no fallback.')
    config = configuration(name)
    if name == 'ollama' and config.model != 'qwen3-vl:8b-instruct':
        raise ValueError('Select the exact local Qwen3-VL 8B instruct model.')
    from dataclasses import replace
    from services.assessment import ENGINE_VERSION
    return replace(config, version=ENGINE_VERSION)
