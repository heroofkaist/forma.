"""One explicitly approved synthetic assessment request; local PostgreSQL only.

No worker, document inference, retries, publication, dotenv or production access.
Run --help before configuring. A second invocation is a second paid request.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit


def configure():
    url = urlsplit(os.getenv('FORMA_DATABASE_URL', ''))
    if (url.scheme not in {'postgresql', 'postgresql+psycopg'} or
        url.hostname not in {'localhost', '127.0.0.1', '::1'} or
        url.path != '/forma_cloud_pilot' or url.query or url.fragment):
        raise ValueError('Use a dedicated loopback PostgreSQL database named forma_cloud_pilot, without URL parameters.')
    os.environ.update({'FORMA_LOAD_ENV_FILE': 'false', 'FORMA_STORAGE_BACKEND': 'local',
        'FORMA_STORAGE_DIR': str(Path('.local/cloud-qwen-pilot/storage').resolve()),
        'FORMA_DOCUMENT_WORKER_ENABLED': 'false', 'FORMA_EMAIL_WORKER_ENABLED': 'false',
        'FORMA_AI_PROVIDER': 'openrouter', 'FORMA_ASSESSMENT_PROVIDER': 'openrouter',
        'FORMA_AI_PAID_ENABLED': 'true', 'FORMA_AI_PAID_FALLBACK_ENABLED': 'false',
        'FORMA_AI_MONTHLY_BUDGET_USD': '4', 'FORMA_AI_MAX_JOB_COST_USD': '0.02',
        'FORMA_AI_MAX_CONCURRENT_REQUESTS': '1', 'GEMINI_API_KEY': ''})


def fixture(config):
    """Create only fixed synthetic source observations, never accept student input."""
    from dataclasses import asdict
    from persistence import (SessionLocal, AcademicCourse, CourseOffering, AssignmentFamily,
                             AcademicAssignment, AcademicSubmission)
    from processing_models import ProcessingJob, DocumentInterpretation
    from assessment_models import AssessmentRubric
    from document_models import SubmissionDocument
    import pymupdf
    token = uuid4().hex
    text = 'Synthetic exercise: mass is 2 kg, acceleration is 3 m/s squared. F = ma = 6 N.'
    criterion = dict(question_id='q1', criterion_id='force', description='Apply F = ma and state force with units.',
        maximum_points=2, performance_descriptions='2: correct calculation and units; 1: partial reasoning; 0: incorrect.',
        feedback_requirements='Quote the calculation.', weight=None, insight_tag='')
    rubric = dict(category='problem_set', instructions='Calculate force for mass 2 kg and acceleration 3 m/s squared. Show formula and units.',
                  reference_material='F = ma = 6 N.', criteria=[criterion])
    section = dict(id='p1-s1', page_number=1, kind='paragraph', transcription=text,
                   readability='readable', evidence_kind='embedded_text')
    with SessionLocal() as db:
        course = AcademicCourse(code='PILOT-' + token[:12], name='Synthetic pilot', instructor='Synthetic', department='Test')
        db.add(course); db.flush()
        offering = CourseOffering(course_id=course.id, academic_year='2026', term='Pilot', section='01', class_code=token)
        family = AssignmentFamily(course_id=course.id, title='Synthetic force'); db.add_all([offering, family]); db.flush()
        assignment = AcademicAssignment(offering_id=offering.id, family_id=family.id, title='Synthetic cloud pilot',
            assignment_type='problem_set', description=rubric['instructions'], maximum_score=2, originality_enabled=False,
            questions=[dict(id='q1', title='Force', statement=rubric['instructions'], maximum_points=2,
                            criteria=[dict(criterion_id='force', description=criterion['description'], maximum_points=2)])])
        db.add(assignment); db.flush()
        relative = 'synthetic-pilot/' + token + '.pdf'
        path = Path(os.environ['FORMA_STORAGE_DIR']) / relative; path.parent.mkdir(parents=True, exist_ok=True)
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((72, 72), text); body = pdf.tobytes(); path.write_bytes(body)
        digest = hashlib.sha256(body).hexdigest()
        submission = AcademicSubmission(assignment_id=assignment.id, student_id='synthetic-pilot', student_name='Synthetic only',
            file_path=relative, file_name='synthetic-force.pdf', file_type='pdf')
        db.add(submission); db.flush()
        db.add(SubmissionDocument(submission_id=submission.id, content_hash=digest,
            structure={'pages': [{'number': 1, 'unit': 'page', 'text': text}], 'unit_count': 1, 'warnings': []}))
        source_job = ProcessingJob(submission_id=submission.id, requested_by='synthetic-pilot', input_hash=hashlib.sha256((token+'source').encode()).hexdigest(),
            content_hash=digest, model='deterministic-synthetic', prompt_version='synthetic-v1', context={},
            status='needs_review', stage='review', usage={'ai_called': False, 'synthetic_only': True})
        db.add(source_job); db.flush()
        observed = DocumentInterpretation(submission_id=submission.id, job_id=source_job.id,
            result={'document_type': 'problem_set', 'sections': [section], 'warnings': ['Deterministic synthetic observations; no document inference.'],
                    'question_associations': [], 'requires_human_review': True})
        approved = AssessmentRubric(assignment_id=assignment.id, spec=rubric, approved_by='synthetic-pilot-operator')
        db.add_all([observed, approved]); db.flush()
        snapshot = dict(title=assignment.title, rubric_id=approved.id, rubric=rubric, interpretation_id=observed.id,
            correction_id=None, source={'sections': [section]}, source_limitations={'synthetic_only': True, 'teacher_confirmed': False})
        job = ProcessingJob(submission_id=submission.id, requested_by='synthetic-pilot', input_hash=hashlib.sha256(token.encode()).hexdigest(),
            content_hash=digest, model=config.model, prompt_version=config.version, status='interpreting', stage='interpreting', attempts=1,
            context={'task': 'assessment', 'assessment': snapshot, 'ai': asdict(config)})
        db.add(job); db.flush(); db.commit()
        return job.id, snapshot


def run():
    configure()
    from persistence import engine, SessionLocal, init_db
    from migrations import apply_migrations
    from services.ai_providers.engine import assessment_configuration
    from services.ai_providers.openrouter import BASE, secret
    from services.assessment import evaluate
    from processing_models import ProcessingJob
    from assessment_models import AssessmentSuggestion
    from budget_models import AIRequestCharge
    from sqlalchemy import select
    from scripts.reconcile_ai_billing import reconcile
    import httpx
    config = assessment_configuration()
    # Imports register all tables before creating this dedicated local database.
    init_db(); apply_migrations(engine)
    job_id, snapshot = fixture(config)
    print(json.dumps({'job_id': job_id, 'synthetic_only': True, 'maximum_request_usd': '0.02'}), flush=True)
    try:
        result, usage = evaluate(snapshot, config, job_id=job_id)
        with SessionLocal() as db:
            job = db.get(ProcessingJob, job_id)
            db.add(AssessmentSuggestion(submission_id=job.submission_id, job_id=job_id, rubric_id=snapshot['rubric_id'],
                interpretation_id=snapshot['interpretation_id'], result=result))
            job.status = 'needs_review'; job.stage = 'review'; job.usage = usage; db.commit()
    except Exception:
        with SessionLocal() as db:
            job = db.get(ProcessingJob, job_id); job.status = 'failed'; job.stage = 'failed'; db.commit()
        raise
    # Metadata GET only: independently verify the generation receipt in the same ledger.
    with SessionLocal() as db:
        charges = db.scalars(select(AIRequestCharge).where(AIRequestCharge.job_id == job_id)).all()
        if len(charges) != 1: raise ValueError('Expected exactly one durable reservation.')
        charge_id = charges[0].id
    with httpx.Client(base_url=BASE, headers={'Authorization': 'Bearer ' + secret()},
                      timeout=15, trust_env=False, follow_redirects=False) as client:
        billing = reconcile(client, charge_id)
    if billing['cost_state'] != 'settled' or billing['overrun']:
        raise ValueError('Billing requires operator review; do not retry inference.')
    print(json.dumps({'job_id': job_id, 'provider': config.name, 'model': config.model,
        'endpoint': config.options['endpoint'], 'billing': billing, 'published': False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approve-one-paid-request', action='store_true',
                        help='Explicit operator approval for one synthetic paid request, up to USD 0.02.')
    args = parser.parse_args()
    if not args.approve_one_paid_request:
        parser.error('No request made. Explicit --approve-one-paid-request is required.')
    try: run()
    except Exception as error:
        raise SystemExit('Pilot stopped (' + type(error).__name__ + '). Do not rerun blindly; inspect the ledger and reconcile existing charges.') from None


if __name__ == '__main__': main()
