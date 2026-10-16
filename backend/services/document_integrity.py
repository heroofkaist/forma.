"""Bounded, deterministic document signals. No network, model, tokens or authorship score.

These are inspectable text observations, not a trained authorship classifier. In
particular, sentence regularity and lexical diversity never trigger a finding.
"""
import re
import statistics
import unicodedata
from collections import Counter

VERSION = 'local-text-signals-v1'
MAX_INPUT_BYTES = 500_000
WORD = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*", re.UNICODE)
ARTIFACTS = (
    ('model_disclosure', re.compile(r'\b(?:as an? (?:AI|artificial intelligence)(?: language)? model|I am an? (?:AI|artificial intelligence)(?: language)? model|как (?:языковая модель|модель (?:ИИ|искусственного интеллекта))|я (?:языковая модель|модель (?:ИИ|искусственного интеллекта)))\b', re.I),
     'В тексте есть фраза, в которой автор представляется моделью ИИ.',
     'Это может быть цитата, пример из задания или предмет исследования.'),
    ('chat_markup', re.compile(r'<\|(?:im_start|im_end|start_header_id|end_header_id|eot_id)\|>|\[/?INST\]|(?:cite[^\n]{1,120}?)'),
     'В документ попала служебная разметка диалога или ссылки из интерфейса ИИ.',
     'Разметку могли скопировать как пример или для обсуждения; проверьте контекст.'),
)


def evaluate(structure, category, config=None, job_id=None, progress=None, checkpoints=None, checkpoint=None):
    pages = structure.get('pages', [])
    size = sum(len(p.get('text', '').encode()) for p in pages)
    readable = [p for p in pages if p.get('text', '').strip()]
    base = {'version': VERSION, 'provider': 'local', 'model': VERSION, 'method': 'deterministic_text_rules',
        'status': 'completed', 'detector_status': 'advisory', 'features': [], 'style_signals': [],
        'units_total': len(pages), 'units_analyzed': 0, 'chunks_total': len(readable), 'chunks_analyzed': 0,
        'authorship_probability': None, 'all_findings_unverified': True, 'metrics': {},
        'limitations': ['Алгоритм не устанавливает авторство и не распознаёт все виды генерации ИИ.',
            'Анализируется извлечённый текст; текст на изображениях и нераспознанных сканах не проверяется.',
            'Отсутствие признаков не подтверждает, что работа написана без ИИ.']}
    usage = {'ai_called': False, 'local_analysis': True, 'provider': 'local', 'model': VERSION, 'cost_usd': '0.00'}
    if size > MAX_INPUT_BYTES:
        return {**base, 'status': 'input_limit', 'detector_status': 'not_analyzed'}, usage
    if not readable:
        return {**base, 'status': 'no_readable_text', 'detector_status': 'insufficient_text'}, usage
    signals, paragraphs, words, sentence_lengths = [], {}, [], []
    seen_artifacts = set()
    prose = category in {'essay', 'lab_report', 'research_report', 'general', 'presentation'}
    for page in readable:
        if progress: progress()
        text, unit = page['text'], page['number']
        page_words = WORD.findall(text.casefold())
        words.extend(page_words)
        sentence_lengths.extend(len(WORD.findall(s)) for s in re.split(r'[.!?。！？]+(?:\s+|$)', text) if len(WORD.findall(s)) >= 4)
        for code, pattern, observation, alternative in ARTIFACTS:
            match = pattern.search(text)
            if match and code not in seen_artifacts:
                seen_artifacts.add(code)
                # Quote exact text, including enough context to inspect quoted examples.
                quote = text[max(0, match.start()-70):min(len(text), match.end()+120)]
                signals.append({'code': code, 'unit': unit, 'quote': quote,
                    'observation': observation, 'alternative_explanation': alternative})
        if prose:
            for paragraph in re.split(r'\n\s*\n', text):
                tokens = WORD.findall(unicodedata.normalize('NFKC', paragraph).casefold())
                if len(tokens) < 40: continue  # Running headers and short formulae do not count.
                # Keep numbers/punctuation: repeated lab phrasing with different
                # measurements is not the same passage.
                key = ' '.join(unicodedata.normalize('NFKC', paragraph).casefold().split())
                if key in paragraphs:
                    first_unit = paragraphs[key]
                    if not any(s['code'] == 'repeated_passage' for s in signals):
                        signals.append({'code': 'repeated_passage', 'unit': unit, 'quote': paragraph[:300],
                            'observation': f'Найден повтор длинного фрагмента (первое вхождение: раздел {first_unit}; пробелы и регистр не учитываются).',
                            'alternative_explanation': 'Повтор может быть намеренным, результатом копирования, шаблона или извлечения текста. Сам по себе он не указывает на ИИ.'})
                else: paragraphs[key] = unit
    counts = Counter(words)
    metrics = {'word_count': len(words), 'sentence_count': len(sentence_lengths),
        'lexical_diversity': round(len(counts)/len(words), 4) if words else None,
        'mean_sentence_words': round(statistics.mean(sentence_lengths), 2) if sentence_lengths else None,
        'sentence_length_cv': round(statistics.pstdev(sentence_lengths)/statistics.mean(sentence_lengths), 4) if len(sentence_lengths) >= 5 else None}
    enough = len(words) >= 200
    if not prose:
        base['limitations'].append('Для задач, формул и кода статистика стиля не позволяет оценивать авторство.')
    if not enough:
        base['limitations'].append('Мало текста для устойчивого описания стиля (менее 200 слов).')
    # Explicit artifacts remain inspectable even in a short text or code hand-in.
    applicable = any(s['code'] != 'repeated_passage' for s in signals) or (prose and enough)
    return {**base, 'style_signals': signals[:12], 'metrics': metrics,
        'units_analyzed': len(readable), 'chunks_analyzed': len(readable),
        'detector_status': 'advisory' if applicable else 'not_applicable' if not prose else 'insufficient_text'}, usage
