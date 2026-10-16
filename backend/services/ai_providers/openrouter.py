"""Explicitly opted-in, privacy-routed, budget-reserved Qwen cloud transport."""
import io
import json
import math
import os
from datetime import datetime, timezone
from decimal import Decimal
from PIL import Image
import httpx
import ai_budget
from .qwen import SYSTEM, PageObservations, interpret_pages
from services.processing_diagnostics import set_stage

BASE = 'https://openrouter.ai/api/v1'
MODEL = 'qwen/qwen3-vl-8b-instruct'


class CloudConfigurationError(ValueError):
    pass


def secret():
    key = os.getenv('FORMA_OPENROUTER_API_KEY', '').strip()
    if not key: raise CloudConfigurationError('The backend OpenRouter key is not configured.')
    return key


def metadata_get(client, path):
    response = client.get(path)
    if response.status_code == 402:
        ai_budget.pause_provider()
        raise ai_budget.BudgetUnavailable('Provider credit is unavailable; paid inference is paused pending review.')
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict): raise CloudConfigurationError('Invalid provider metadata.')
    return value


def verify_key(client):
    data = metadata_get(client, '/key').get('data', {})
    try:
        _, limit = ai_budget.money(data.get('limit'))
        _, remaining = ai_budget.money(data.get('limit_remaining'))
    except ValueError as error:
        raise CloudConfigurationError('A finite dedicated monthly key limit is required.') from error
    if data.get('is_management_key') is not False or ai_budget.money(data.get('byok_usage_monthly'))[1] != 0:
        raise CloudConfigurationError('Use a dedicated non-management key without BYOK usage.')
    if data.get('limit_reset') != 'monthly' or not 0 < limit <= ai_budget.HARD_MONTH:
        raise CloudConfigurationError('The dedicated provider key must have a monthly limit no greater than USD 4.')
    return remaining


def check_receipt(data):
    usage = data.get('usage') if isinstance(data.get('usage'), dict) else {}
    return usage.get('cost'), {k: usage.get(k) for k in ('prompt_tokens', 'completion_tokens')}


def endpoint_rates(client, config):
    endpoints = metadata_get(client, '/models/' + MODEL + '/endpoints').get('data', {}).get('endpoints', [])
    chosen = next((e for e in endpoints if e.get('tag') == config.options['endpoint']), None)
    if chosen is None or not {'response_format', 'structured_outputs', 'max_tokens'}.issubset(chosen.get('supported_parameters', [])):
        raise CloudConfigurationError('The exact allowed endpoint is unavailable or lacks required structured-output parameters.')
    pricing = chosen.get('pricing', {})
    try:
        prompt = ai_budget.money(pricing.get('prompt'))[0]
        completion = ai_budget.money(pricing.get('completion'))[0]
        if any(ai_budget.money(v)[0] != 0 for k, v in pricing.items() if k not in {'prompt', 'completion', 'discount', 'input_cache_read'}):
            raise ValueError('Additional billable pricing is unsupported.')
    except ValueError as error:
        raise CloudConfigurationError('Endpoint pricing cannot be safely bounded.') from error
    if prompt * 1_000_000 > Decimal(config.options['prompt_price_cap']) or completion * 1_000_000 > Decimal(config.options['completion_price_cap']):
        raise ai_budget.BudgetUnavailable('The allowed endpoint exceeds configured price caps.')
    return chosen, prompt, completion


def strict_schema(schema=None):
    import copy
    schema = copy.deepcopy(schema if schema is not None else PageObservations.model_json_schema())
    def visit(node):
        if isinstance(node, dict):
            node.pop('default', None)
            if 'properties' in node: node['required'] = list(node['properties'])
            for value in node.values(): visit(value)
        elif isinstance(node, list):
            for value in node: visit(value)
    visit(schema)
    return schema


def estimate(messages, schema, images, output_tokens, prompt_rate, completion_rate):
    # Conservative admission estimate, NOT actual image billing or a guarantee:
    # UTF-8 byte upper allowance + framing, plus 4 unmerged 16x16 patch grids per
    # bounded image. Actual provider preprocessing/accounting may differ. Reserve
    # the WHOLE remaining job ceiling and retain the provider key cap as backstop.
    text_bytes = len(json.dumps([messages, schema], ensure_ascii=False).encode('utf8'))
    image_tokens = 0
    import base64
    for value in images:
        with Image.open(io.BytesIO(base64.b64decode(value, validate=True))) as image:
            w, h = image.size
            if max(w, h) > 1400: raise CloudConfigurationError('Cloud image resolution exceeds the hard limit.')
            image_tokens += 4 * math.ceil(w/16) * math.ceil(h/16) + 512
    tokens = text_bytes + 2048 + image_tokens
    return ai_budget.money(tokens*prompt_rate + output_tokens*completion_rate)[1]


class OpenRouterProvider:
    def interpret(self, request, progress=None, observe=None):
        return self._run(request.config, request.job_id,
            lambda chat: interpret_pages(request, chat, progress, observe))

    def complete(self, config, job_id, schema, system, context, progress=None, images=None):
        def run(chat):
            if progress: progress()
            result = chat(images or [], context, config.options['timeout'])
            if progress: progress()
            return result
        return self._run(config, job_id, run, schema, system)

    def _run(self, config, job_id, run, schema=None, system=SYSTEM):
        ai_budget.assert_dispatch_allowed()
        if config.model != MODEL:
            raise CloudConfigurationError('Only the exact configured Qwen3-VL 8B model is supported.')
        if os.getenv('FORMA_OPENROUTER_PRIVACY_ACKNOWLEDGED', 'false').lower() != 'true':
            raise CloudConfigurationError('Operator privacy review is required before cloud document transmission.')
        options = config.options
        with httpx.Client(base_url=BASE, headers={'Authorization': 'Bearer ' + secret()},
                          trust_env=False, follow_redirects=False,
                          timeout=httpx.Timeout(options['timeout'], connect=5)) as client:
            set_stage('openrouter_preflight')
            verify_key(client)
            selected, prompt_rate, completion_rate = endpoint_rates(client, config)
            def chat(images, context, timeout):
                if len(images) > 3: raise CloudConfigurationError('Too many cloud page images.')
                response_schema = strict_schema(schema)
                user = json.dumps(context, ensure_ascii=False)
                if len(user.encode('utf8')) > 16000 or len(system.encode('utf8')) > 8000:
                    raise CloudConfigurationError('Cloud prompt exceeds the bounded request budget.')
                required = estimate([system, user], response_schema, images, options['output_tokens'], prompt_rate, completion_rate)
                # Verify provider-side remaining credit before reserving/sending.
                provider_remaining = verify_key(client)
                charge = ai_budget.reserve(job_id, 'openrouter', MODEL, required, timeout=math.ceil(timeout), provider_remaining=provider_remaining)
                payload = {'model': MODEL, 'stream': False, 'max_tokens': options['output_tokens'], 'temperature': 0,
                    'provider': {'only': [options['endpoint']], 'order': [options['endpoint']], 'allow_fallbacks': False,
                                 'require_parameters': True, 'data_collection': 'deny', 'zdr': True,
                                 'max_price': {'prompt': float(options['prompt_price_cap']), 'completion': float(options['completion_price_cap']), 'request': 0, 'image': 0}},
                    'response_format': {'type': 'json_schema', 'json_schema': {'name': 'forma_structured_result', 'strict': True, 'schema': response_schema}},
                    'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': [{'type': 'text', 'text': user}] +
                        [{'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + image}} for image in images]}]}
                if len(json.dumps(payload).encode('utf8')) > 12*1024*1024:
                    # No HTTP was attempted; this reservation can be proven free.
                    ai_budget.record(charge, cost='0')
                    raise CloudConfigurationError('Encoded cloud payload exceeds 12 MB.')
                set_stage('openrouter_request')
                try:
                    response = client.post('/chat/completions', json=payload, timeout=timeout,
                                           headers={'X-Request-ID': charge})
                    if response.status_code == 402:
                        ai_budget.record(charge, blocked_reason='provider_402')
                        raise ai_budget.BudgetUnavailable('Provider credit is unavailable; paid inference is paused pending review.')
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict): raise CloudConfigurationError('Provider returned no response object.')
                except ai_budget.BudgetUnavailable:
                    raise
                except Exception as error:
                    # Includes timeout/read errors and response decoding. A sent
                    # request is not assumed free; no automatic resend occurs.
                    ai_budget.record(charge)
                    raise ai_budget.BudgetUnavailable('Provider billing is uncertain; the reservation is held for reconciliation.') from error
                cost, tokens = check_receipt(data)
                created = data.get('created'); billed = None
                if type(created) is int:
                    try: billed = datetime.fromtimestamp(created, timezone.utc).strftime('%Y-%m')
                    except (ValueError, OverflowError, OSError): pass
                billing = ai_budget.record(charge, cost=cost, generation_id=data.get('id'), tokens=tokens, billed_month=billed)
                if billing['overrun']: raise ai_budget.BudgetUnavailable('Reported billing exceeded its reservation; paid requests are paused.')
                if data.get('model') != MODEL or (data.get('provider') and (not isinstance(data['provider'], str) or data['provider'].casefold() != selected['provider_name'].casefold())):
                    raise CloudConfigurationError('Provider returned an unexpected model or endpoint identity.')
                if data.get('error'): raise CloudConfigurationError('Provider returned an unsuccessful generation.')
                choices = data.get('choices', [])
                if not choices: raise CloudConfigurationError('Provider returned no completion.')
                choice = choices[0]
                return {'done': True, 'done_reason': choice.get('finish_reason'),
                        'message': {'content': choice.get('message', {}).get('content')},
                        'prompt_eval_count': tokens.get('prompt_tokens'), 'eval_count': tokens.get('completion_tokens'),
                        '_billing': billing}
            return run(chat)
