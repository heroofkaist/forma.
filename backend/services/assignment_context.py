"""Teacher requirements and answer grouping shared by reading and assessment."""
import hashlib
import json
import re
from sqlalchemy import select

VERSION = 'assignment-guided-v1'


def answer_groups(questions, category):
    groups = []
    for q in questions:
        criteria = q.get('criteria', [])
        # Historic forms stored several problem-specific criteria under one question.
        numbered = {}
        for c in criteria:
            match = re.search(r'(?:задач[аеиу]?|вопрос|задани[ея]|problem|question|task)\s*(?:№\s*)?(\d+|[IVX]{1,8}|[A-Za-zА-Яа-я])\b', c['description'], re.I)
            if match: numbered.setdefault(match[1], []).append(c)
        split = category in {'problem_set', 'homework'} and len(questions) == 1 and len(numbered) > 1 and sum(map(len, numbered.values())) == len(criteria)
        sets = [(f'{q["id"]}-task-{n}', f'Задача {n}', cs) for n, cs in numbered.items()] if split else [(q['id'], q['title'], criteria)]
        for identifier, title, members in sets:
            groups.append({'id': identifier, 'question_id': q['id'], 'title': title, 'statement': q.get('statement', ''),
                'criterion_ids': [c.get('criterion_id', c.get('id')) for c in members], 'criteria': members,
                'maximum_points': sum(c['maximum_points'] for c in members) if split else q.get('maximum_points'),
                'mode': 'problem_criteria' if split else 'question' if len(questions) > 1 else 'whole_work'})
    return groups


def assignment_snapshot(db, assignment):
    from processing_models import AssignmentBrief
    files = db.scalars(select(AssignmentBrief).where(AssignmentBrief.assignment_id == assignment.id).order_by(AssignmentBrief.created_at.desc(), AssignmentBrief.id.desc())).all()
    return {'version': VERSION, 'title': assignment.title, 'category': assignment.assignment_type,
        'instructions': assignment.description, 'answer_groups': answer_groups(assignment.questions, assignment.assignment_type),
        'files': [{'id': f.id, 'name': f.file_name, 'path': f.file_path, 'file_type': f.structure['file_type'],
            'text': f.structure.get('extracted_text', ''), 'pages': len(f.structure.get('pages', [])),
            'scan_pages': [p['number'] for p in f.structure.get('pages', []) if not p.get('text','').strip()],
            'limitations': list(dict.fromkeys(f.structure.get('warnings',[]))),
            'hash': f.structure.get('content_hash'), 'questions': f.approved_questions or f.proposed_questions,
            'approved_questions': f.approved_questions} for f in files]}


def compact_context(snapshot, maximum=6000):
    """Keep identities and maxima. Report any shortened teacher material explicitly."""
    result = {'title': snapshot.get('title', ''), 'instructions': snapshot.get('instructions', ''),
        'answer_groups': snapshot.get('answer_groups', []),
        'files': [{**{k: f[k] for k in ('id', 'name', 'text', 'pages')}, 'limitations':f.get('limitations',[]),
            'teacher_clarifications':f.get('approved_questions',[])} for f in snapshot.get('files', [])]}
    original = json.dumps(result, ensure_ascii=False)
    size = 1600
    while len(json.dumps(result, ensure_ascii=False).encode()) > maximum and size >= 24:
        def shorten(value, key=''):
            if isinstance(value, str): return value if key in {'id', 'question_id', 'criterion_id', 'criterion_ids', 'mode'} else value[:size]
            if isinstance(value, list): return [shorten(v, key) for v in value]
            if isinstance(value, dict): return {k: shorten(v, k) for k, v in value.items()}
            return value
        result = shorten(result); size //= 2
    if len(json.dumps(result, ensure_ascii=False).encode()) > maximum:
        raise ValueError('Too many assignment definitions for this bounded AI request. Review manually or split the assignment.')
    result['context_shortened'] = json.dumps(result, ensure_ascii=False) != original
    return result


def task_images(snapshot, image_edge=1000):
    """At most two scanned task pages, separate from student evidence."""
    import base64
    import pymupdf
    from persistence import read_blob
    images, labels = [], []
    def scanned(f): return f.get('scan_pages', list(range(1,f['pages']+1)) if not f['text'].strip() else [])
    total = sum(len(scanned(f)) for f in snapshot.get('files', []))
    for f in snapshot.get('files', []):
        if not scanned(f) or f['file_type'] != 'pdf': continue
        raw = read_blob(f['path'])
        if f.get('hash') and hashlib.sha256(raw).hexdigest() != f['hash']: raise ValueError('Assignment source changed after scheduling.')
        with pymupdf.open(stream=raw, filetype='pdf') as doc:
            for number in scanned(f)[:2-len(images)]:
                index = number-1
                page = doc[index]; scale = min(1.3, image_edge / max(page.rect.width, page.rect.height))
                images.append(base64.b64encode(page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes('png')).decode())
                labels.append({'file_id': f['id'], 'file_name': f['name'], 'page': index+1})
        if len(images) == 2: break
    return images, labels, total > len(images)
