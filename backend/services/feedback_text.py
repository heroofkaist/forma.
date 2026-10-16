"""Clean generated explanations only. Never rewrite student quotes or originals."""
import math
import re

PLACEHOLDERS = {'null', 'none', 'undefined', 'nan', 'infinity', '-infinity', '[object object]', 'n/a', 'нет данных'}
FALLBACK = 'Модель не дала понятного обоснования. Сверьте этот критерий с оригиналом и выставьте балл вручную.'


def readable(value):
    if not isinstance(value, str): return ''
    value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', value).strip()
    if value.casefold() in PLACEHOLDERS or not value: return ''
    if value.startswith(('{', '[{', '```json')): return ''
    return value


def clean_feedback(value):
    # Structural errors still fail strict validation. Only model prose is repaired;
    # an unusable rationale can REMOVE a score, never justify one.
    if not isinstance(value, dict) or not isinstance(value.get('criteria'), list): return value
    for c in value['criteria']:
        if not isinstance(c, dict): continue
        rationale = readable(c.get('rationale'))
        bad_score = isinstance(c.get('proposed_score'), float) and not math.isfinite(c['proposed_score'])
        if not rationale or bad_score:
            c['proposed_score'] = None
            c['finding'] = 'insufficient_evidence'
            c['rationale'] = rationale or FALLBACK
            c['uncertainty'] = [FALLBACK, *c.get('uncertainty', [])[:9]] if isinstance(c.get('uncertainty', []), list) else [FALLBACK]
        else: c['rationale'] = rationale
        c['interpretation'] = readable(c.get('interpretation')) or 'Проверьте приведённые фрагменты оригинала.'
        c['suggested_improvement'] = readable(c.get('suggested_improvement'))
        for field in ('uncertainty', 'missing_evidence'):
            if isinstance(c.get(field), list): c[field] = [text for item in c[field] if (text := readable(item))]
    return value
