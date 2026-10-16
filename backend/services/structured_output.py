"""Decode a single complete model object without inventing or rewriting its data."""
import json
import re
from services.assessment_errors import AssessmentValidationError


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result: raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def model_object(raw):
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 200000:
        raise AssessmentValidationError('document_output_invalid_json')
    text = raw.lstrip('\ufeff').strip()
    # Some compatible providers still wrap structured output in a completed
    # reasoning block or Markdown fence. Removing a wrapper preserves every
    # character inside JSON strings, including original quotations and LaTeX.
    text = re.sub(r'^<think>[\s\S]*?</think>\s*', '', text, count=1)
    fenced = re.fullmatch(r'```(?:json)?\s*([\s\S]*?)\s*```', text, re.I)
    if fenced: text = fenced[1]
    elif text.startswith('```'): raise AssessmentValidationError('document_output_invalid_json')
    def invalid_constant(value): raise ValueError('Nonfinite JSON number')
    decoder = json.JSONDecoder(object_pairs_hook=_pairs, parse_constant=invalid_constant)
    try:
        # Allow a short prose introduction, never multiple objects or recovered
        # fragments from a truncated array/string. Schema/evidence checks follow.
        start = text.find('{')
        if start < 0 or start > 300 or '{' in text[:start] or '[' in text[:start]: raise ValueError('No complete object')
        value, end = decoder.raw_decode(text, start)
        if text[end:].strip() or not isinstance(value, dict): raise ValueError('Extra model output')
        return value
    except (ValueError, RecursionError) as error:
        raise AssessmentValidationError('document_output_invalid_json') from error
