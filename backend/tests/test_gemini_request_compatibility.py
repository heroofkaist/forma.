"""Regression for live-isolated response_schema HTTP 400 incompatibilities."""
import json
import httpx
import pytest
import pymupdf
from google.genai.errors import ClientError
from pydantic import ValidationError
from services import document_understanding as understanding
from services.processing_diagnostics import log_failure, set_stage


def nodes(value):
    if isinstance(value, dict):
        yield value
        for item in value.values(): yield from nodes(item)
    elif isinstance(value, list):
        for item in value: yield from nodes(item)


def test_provider_schema_retains_types_and_local_constraints():
    original = understanding.Interpretation.model_json_schema()
    provider = understanding.provider_response_schema()
    assert all('additionalProperties' not in node and 'maxItems' not in node for node in nodes(provider))
    assert original['additionalProperties'] is False
    assert original['properties']['sections']['maxItems'] == 1000
    assert provider['properties']['sections']['items'] == original['properties']['sections']['items']
    assert provider['$defs']['Section']['properties']['transcription']['maxLength'] == 20000
    assert provider['$defs']['Section']['properties']['page_number']['minimum'] == 1
    assert provider['$defs']['Section']['properties']['kind']['enum'] == original['$defs']['Section']['properties']['kind']['enum']
    assert provider['$defs']['Association']['required'] == original['$defs']['Association']['required']
    assert understanding.Interpretation.model_json_schema() == original


@pytest.mark.parametrize('invalid', ['extra', 'array_limit', 'nested_extra'])
def test_provider_adapter_does_not_weaken_local_validation(invalid):
    result = {'document_type': 'problem_set', 'sections': [], 'question_associations': [], 'warnings': []}
    if invalid == 'extra': result['correctness_score'] = 100
    elif invalid == 'array_limit': result['warnings'] = ['too many'] * 201
    else:
        result['sections'] = [{'id': 's1', 'page_number': 1, 'kind': 'answer', 'evidence_kind': 'embedded_text', 'unapproved_field': 'no'}]
    with pytest.raises(ValidationError): understanding.Interpretation.model_validate(result)


def test_actual_sdk_wire_request_avoids_rejected_fields_and_validates_page_evidence(monkeypatch):
    pdf = pymupdf.open(); pdf.new_page().insert_text((40, 60), 'Question 1\nF = ma'); content = pdf.tobytes(); pdf.close()
    structure = {'unit_count': 1, 'pages': [{'number': 1, 'unit': 'page', 'text': 'Question 1\nF = ma'}], 'warnings': []}
    questions = [{'id': 'q1', 'title': 'Question 1', 'statement': 'State the force equation.'}]
    expected = understanding.deterministic_interpretation(structure, questions, 'problem_set')
    bodies = []
    def respond(request):
        body = json.loads(request.content); bodies.append(body)
        config = body['generationConfig']
        schema = config['responseSchema']
        # These wire fields caused rejection in the real synthetic A/B probes.
        bad = any(any(key in node for key in ('additional_properties', 'additionalProperties', 'max_items', 'maxItems')) for node in nodes(schema))
        if bad:
            return httpx.Response(400, json={'error': {'code': 400, 'status': 'INVALID_ARGUMENT', 'message': 'Unknown name "additional_properties" at generation_config.response_schema.'}})
        assert config['responseMimeType'] == 'application/json'
        assert config['temperature'] == .1 and config['maxOutputTokens'] == 12000
        assert body['contents'][0]['role'] == 'user'
        return httpx.Response(200, json={'candidates': [{'content': {'parts': [{'text': json.dumps(expected)}]}, 'finishReason': 'STOP'}]})
    real_client = understanding.genai.Client
    def client(**kwargs):
        kwargs['http_options'].httpx_client = httpx.Client(transport=httpx.MockTransport(respond))
        return real_client(**kwargs)
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-test-key')
    monkeypatch.setattr(understanding.genai, 'Client', client)
    result, usage = understanding.gemini_interpret(content, 'pdf', structure, questions, 'problem_set', 'gemini-flash-lite-latest', 1)
    assert len(bodies) == 1 and usage['ai_called']
    assert result['sections'][0]['page_number'] == 1 and result['sections'][0]['question_id'] == 'q1'
    assert result['requires_human_review']


def test_allowlisted_provider_reason_never_logs_response_or_private_values(caplog):
    private = 'student@example.com secret-key https://signed.example/private?token=secret'
    error = ClientError(400, {'error': {'status': 'INVALID_ARGUMENT', 'message': f'Unknown name "additional_properties" at generation_config.response_schema. {private}', 'details': [{'private': private}]}})
    set_stage('gemini_request')
    log_failure(error, job_id='synthetic-job')
    record = json.loads(caplog.records[-1].message)
    assert record['provider_status'] == 400
    assert record['provider_reason'] == 'UNKNOWN_SCHEMA_FIELD'
    assert record['provider_fields'] == ['generation_config.response_schema.additional_properties']
    assert private not in caplog.text and 'details' not in record
    # Do not copy arbitrary field paths, status labels or hints from the provider.
    caplog.clear()
    error = ClientError(400, {'error': {'status': private, 'message': f'Unknown name "{private}" at generation_config.response_schema.'}})
    log_failure(error, job_id='synthetic-job')
    record = json.loads(caplog.records[-1].message)
    assert 'provider_reason' not in record and 'provider_fields' not in record
    assert private not in caplog.text


def test_live_synthetic_schema_when_explicit_test_key_is_configured(monkeypatch):
    import os
    from google import genai
    from google.genai import types
    key = os.getenv('FORMA_TEST_GEMINI_API_KEY')
    if not key:
        pytest.skip('Set FORMA_TEST_GEMINI_API_KEY for a bounded synthetic live compatibility check.')
    with genai.Client(api_key=key, http_options=types.HttpOptions(timeout=30000, retry_options=types.HttpRetryOptions(attempts=1))) as client:
        response = client.models.generate_content(
            model=os.getenv('GEMINI_MODEL', 'gemini-flash-lite-latest'),
            contents='Synthetic compatibility test: return document_type problem_set, empty sections, empty question_associations, empty warnings and requires_human_review true.',
            config=types.GenerateContentConfig(response_mime_type='application/json', response_schema=understanding.provider_response_schema(), temperature=.1, max_output_tokens=12000),
        )
    result = understanding.validate_result(json.loads(response.text), {'pages': []}, [])
    assert result['requires_human_review']
