"""Copy saved synthetic Phase 4 data for UI review; never runs inference.

Adds one clearly labelled deterministic, three-page UI fixture in the copy.
Existing saved assessment artifacts and all production data remain untouched.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    source = repo / 'artifacts/assessment-phase-4/run-03'
    if not json.loads((source / 'report.json').read_text()).get('synthetic_only'):
        raise SystemExit('Expected the existing synthetic Phase 4 fixture.')
    root = args.output.resolve()
    if root.exists(): raise SystemExit('Choose a new output directory; existing data is never overwritten.')
    root.mkdir(parents=True)
    with sqlite3.connect((source / 'benchmark.sqlite3').as_uri() + '?mode=ro', uri=True) as original:
        with sqlite3.connect(root / 'benchmark.sqlite3') as target: original.backup(target)
    shutil.copytree(source / 'storage', root / 'storage')
    from dotenv import dotenv_values
    settings = {k: v for k, v in dotenv_values(source / 'runtime.env').items() if v is not None}
    settings.update({'FORMA_DATABASE_URL': 'sqlite:///' + str(root / 'benchmark.sqlite3'), 'FORMA_STORAGE_DIR': str(root / 'storage'),
        'FORMA_LOAD_ENV_FILE': 'false', 'FORMA_DOCUMENT_WORKER_ENABLED': 'false', 'FORMA_EMAIL_WORKER_ENABLED': 'false',
        'FORMA_AI_PAID_ENABLED': 'false', 'FORMA_OPENROUTER_API_KEY': '', 'GEMINI_API_KEY': '', 'FORMA_OLLAMA_BASE_URL': 'http://127.0.0.1:9'})
    os.environ.update(settings)
    (root / 'runtime.env').write_text('\n'.join(f'{k}={v}' for k, v in settings.items()) + '\n')
    import pymupdf
    from sqlalchemy import select
    from persistence import SessionLocal, AcademicAssignment, AcademicSubmission
    from document_models import SubmissionDocument
    from processing_models import DocumentInterpretation, ProcessingJob
    from assessment_models import AssessmentRubric, AssessmentSuggestion
    with SessionLocal() as db:
        base = db.scalar(select(AcademicAssignment).where(AcademicAssignment.title == 'essay-strong'))
        original = db.scalar(select(AcademicSubmission).where(AcademicSubmission.assignment_id == base.id))
        criteria = [
            {'criterion_id': 'argument', 'description': 'Тезис и логика аргумента', 'maximum_points': 5},
            {'criterion_id': 'evidence', 'description': 'Доказательства и контраргументы', 'maximum_points': 5},
            {'criterion_id': 'conclusions', 'description': 'Выводы и ограничения', 'maximum_points': 5},
        ]
        instructions = 'Сопоставьте примеры аргументации. Оцените ясность позиции, качество доказательств и обоснованность выводов. Это детерминированный пример интерфейса; модель не запускалась.'
        assignment = AcademicAssignment(offering_id=base.offering_id, family_id=base.family_id, title='Аргументация и работа с доказательствами', assignment_type='essay', description=instructions, maximum_score=15, originality_enabled=False,
            questions=[{'id': 'q1', 'title': 'Анализ работы', 'statement': instructions, 'maximum_points': 15, 'criteria': criteria}])
        db.add(assignment); db.flush()
        pdf = pymupdf.open()
        texts = []
        for name in ('essay-strong', 'essay-weak', 'lab-uncertainty'):
            with pymupdf.open(source / (name + '.pdf')) as page: pdf.insert_pdf(page); texts.append(page[0].get_text())
        body = pdf.tobytes(); pdf.close(); path = 'review-ui-fixture/three-pages.pdf'
        target = root / 'storage' / path; target.parent.mkdir(parents=True); target.write_bytes(body)
        submission = AcademicSubmission(assignment_id=assignment.id, student_id=original.student_id, student_name='Учебный пример · не реальный студент', file_path=path, file_name='Аргументация — учебный пример.pdf', file_type='pdf')
        db.add(submission); db.flush()
        digest = hashlib.sha256(body).hexdigest()
        pages = [{'number': i + 1, 'unit': 'page', 'text': text} for i, text in enumerate(texts)]
        db.add(SubmissionDocument(submission_id=submission.id, content_hash=digest, structure={'pages': pages, 'unit_count': 3, 'warnings': []}))
        sections = [{'id': f'p{i + 1}-s1', 'page_number': i + 1, 'kind': 'paragraph', 'transcription': text, 'readability': 'readable', 'evidence_kind': 'embedded_text', 'question_id': 'q1', 'rationale': 'Детерминированный пример интерфейса.', 'uncertainty_notes': []} for i, text in enumerate(texts)]
        context = {'document_type': 'essay', 'questions': assignment.questions, 'visual_pages': 0}
        understanding = ProcessingJob(submission_id=submission.id, requested_by='synthetic-ui', input_hash=hashlib.sha256((submission.id + 'source').encode()).hexdigest(), content_hash=digest, model='deterministic-ui-fixture', prompt_version='review-ui-fixture', context=context, status='needs_review', stage='review', usage={'ai_called': False, 'ui_fixture': True})
        db.add(understanding); db.flush()
        interpretation = DocumentInterpretation(submission_id=submission.id, job_id=understanding.id, result={'document_type': 'essay', 'sections': sections, 'question_associations': [{'question_id': 'q1', 'section_ids': [s['id'] for s in sections], 'status': 'proposed', 'reason': 'UI fixture'}], 'warnings': ['Детерминированный пример для проверки интерфейса; AI inference не выполнялась.'], 'requires_human_review': True})
        db.add(interpretation); db.flush()
        rubric = AssessmentRubric(assignment_id=assignment.id, approved_by='synthetic-ui', spec={'category': 'essay', 'instructions': instructions, 'reference_material': '', 'criteria': [dict(c, question_id='q1', performance_descriptions='', feedback_requirements='', weight=None, insight_tag='') for c in criteria]})
        db.add(rubric); db.flush()
        snapshot = {'rubric_id': rubric.id, 'rubric': rubric.spec, 'interpretation_id': interpretation.id, 'correction_id': None, 'title': assignment.title, 'source': {'sections': sections}, 'source_limitations': {'ui_fixture': True}}
        job = ProcessingJob(submission_id=submission.id, requested_by='synthetic-ui', input_hash=hashlib.sha256((submission.id + 'assessment').encode()).hexdigest(), content_hash=digest, model='deterministic-ui-fixture', prompt_version='review-ui-fixture', context=dict(context, task='assessment', assessment=snapshot), status='needs_review', stage='review', usage={'ai_called': False, 'ui_fixture': True})
        db.add(job); db.flush()
        findings = [
            ('strength', 4, 'Позиция сформулирована ясно; структура аргумента последовательна.', 'Добавить более точное объяснение связи второго довода с тезисом.'),
            ('insufficient_evidence', None, 'В примере на второй странице утверждение не подкреплено аргументами.', 'Развить доводы и ответить на содержательный контраргумент.'),
            ('concern', 2.5, 'Вывод об отсутствии неопределённости не следует из представленных измерений.', 'Различить случайную вариацию и систематическую погрешность.'),
        ]
        result = {'criteria': [dict(question_id='q1', criterion_id=c['criterion_id'], proposed_score=score, finding=finding, rationale=explanation, interpretation=explanation, evidence=[{'section_id': sections[i]['id'], 'page_number': i + 1, 'quote': texts[i]}], suggested_improvement=improvement, missing_evidence=[], uncertainty=['Пример предназначен только для проверки интерфейса.'], verification_status='needs_review') for i, (c, (finding, score, explanation, improvement)) in enumerate(zip(criteria, findings))]}
        db.add(AssessmentSuggestion(submission_id=submission.id, job_id=job.id, rubric_id=rubric.id, interpretation_id=interpretation.id, result=result)); db.commit()
        receipt = {'synthetic_only': True, 'inference_run': False, 'review_url': '/teacher/submissions/' + submission.id + '/review', 'saved_examples': [{'id': r.id, 'name': r.file_name} for r in db.scalars(select(AcademicSubmission).where(AcademicSubmission.id != submission.id))]}
    (root / 'review-fixture.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False))
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__': main()
