"""Allowlisted worker diagnostics: never format exceptions, locals or source lines."""
import json
import logging
import re
import httpx
from contextvars import ContextVar
from pathlib import PurePath
from botocore.exceptions import ClientError
from google.genai.errors import APIError

logger = logging.getLogger('forma.document_processing')
_stage = ContextVar('document_processing_stage', default='worker_loop')


def set_stage(stage):
    _stage.set(stage)


def get_stage():
    return _stage.get()


def _symbol(value):
    return re.sub(r'[^a-zA-Z0-9_.<>-]', '_', value)[:100]


def safe_provider_reason(error):
    """Return fixed labels only, never a sanitized copy of provider messages."""
    if not isinstance(error, APIError):
        return {}
    result = {}
    if isinstance(error.status, str) and error.status in {'INVALID_ARGUMENT', 'FAILED_PRECONDITION', 'PERMISSION_DENIED', 'UNAUTHENTICATED', 'NOT_FOUND', 'RESOURCE_EXHAUSTED', 'UNAVAILABLE', 'INTERNAL', 'DEADLINE_EXCEEDED'}:
        result['provider_reason'] = error.status
    message = error.message if isinstance(error.message, str) else ''
    # No captured text is emitted. Even a message echoing a private document
    # can produce only these fixed, known schema-field names.
    fields = []
    for field in ('additional_properties', 'additionalProperties', 'max_items', 'maxItems', 'min_length', 'max_length'):
        if f'Unknown name "{field}"' in message and 'generation_config.response_schema' in message:
            fields.append('generation_config.response_schema.' + field)
    if fields:
        result['provider_reason'] = 'UNKNOWN_SCHEMA_FIELD'
        result['provider_fields'] = fields
    return result


def log_failure(error, *, job_id=None, classification='worker_error', retryable=False):
    # Exception strings (including SQL parameters, SDK response bodies and chained
    # errors) can contain credentials or documents. Do NOT use logger.exception,
    # exc_info, format_exception, traceback source text or capture_locals here.
    chains = []
    seen = set()
    current = error
    while current is not None and id(current) not in seen and len(chains) < 5:
        seen.add(id(current))
        frames = []
        trace = current.__traceback__
        while trace is not None:
            code = trace.tb_frame.f_code
            frames.append({'module': _symbol(PurePath(code.co_filename).name),
                           'function': _symbol(code.co_name), 'line': trace.tb_lineno})
            trace = trace.tb_next
        chains.append({'exception_type': _symbol(type(current).__name__), 'frames': frames[-20:]})
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    entry = {'event': 'document_processing_error', 'stage': get_stage(),
             'job_id': job_id, 'exception_type': _symbol(type(error).__name__),
             'classification': classification, 'retryable': retryable,
             'sanitized_traceback': chains}
    # Only numeric status codes / SQLSTATE; never provider text, DB parameters,
    # object keys, URLs, account/submission identity or model output.
    code = getattr(error, 'code', None)
    if type(code) is int and 100 <= code <= 599:
        entry['provider_status'] = code
    entry.update(safe_provider_reason(error))
    if isinstance(error, httpx.HTTPStatusError):
        entry['http_status'] = error.response.status_code
    if isinstance(error, ClientError):
        status = error.response.get('ResponseMetadata', {}).get('HTTPStatusCode')
        if type(status) is int and 100 <= status <= 599:
            entry['storage_status'] = status
        code = error.response.get('Error', {}).get('Code')
        if code in {'AccessDenied', 'InvalidAccessKeyId', 'SignatureDoesNotMatch', 'NoSuchKey', 'NoSuchBucket', 'SlowDown', 'RequestTimeout', 'InternalError', 'ServiceUnavailable', 'Throttling', 'ThrottlingException'}:
            entry['storage_code'] = code
    sqlstate = getattr(getattr(error, 'orig', None), 'sqlstate', None)
    if isinstance(sqlstate, str) and re.fullmatch(r'[0-9A-Z]{5}', sqlstate):
        entry['sqlstate'] = sqlstate
    logger.error(json.dumps(entry, separators=(',', ':')))
