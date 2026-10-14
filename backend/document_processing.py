"""Persistent leased processing. A sleeping Render instance does not run work."""
import hashlib
import json
import os
import threading
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select, update, or_, func, text
from sqlalchemy.exc import IntegrityError
from processing_models import ProcessingJob, DocumentInterpretation, InterpretationCache, AssignmentBrief
from document_models import SubmissionDocument
from persistence import SessionLocal, AcademicSubmission, AcademicAssignment, now_utc, read_blob
from services.document_ingestion import ingest
from services.document_understanding import PROMPT_VERSION, gemini_interpret, limit
from services.ai_grader import configured_model

MAX_ATTEMPTS = 3
ACTIVE = ('extracting', 'interpreting')

class ProcessingLimitError(ValueError):
    pass


def enqueue(db, submission, assignment, actor, force=False):
    if db.bind.dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(62401704)'))
    else:
        db.execute(update(ProcessingJob).where(ProcessingJob.status=='queued').values(stage=ProcessingJob.stage))
    document = db.get(SubmissionDocument, submission.id)
    content_hash = document.content_hash if document else hashlib.sha256(read_blob(submission.file_path)).hexdigest()
    context = {'document_type':assignment.assignment_type, 'questions':[{'id':q['id'], 'title':q['title'], 'statement':q.get('statement',''), 'label':q.get('label','')} for q in assignment.questions], 'visual_pages':limit('FORMA_AI_VISUAL_PAGES',8,12)}
    briefs=db.scalars(select(AssignmentBrief).where(AssignmentBrief.assignment_id==assignment.id).order_by(AssignmentBrief.created_at.desc()).limit(3)).all()
    approved=next((brief.approved_questions for brief in briefs if brief.approved_questions),None)
    if approved: context['questions']=approved
    context['cache_key'] = hashlib.sha256(json.dumps([assignment.offering_id, content_hash, context, PROMPT_VERSION, configured_model()],sort_keys=True).encode()).hexdigest()
    signature = hashlib.sha256(json.dumps([submission.id,content_hash,context,PROMPT_VERSION,configured_model()], sort_keys=True).encode()).hexdigest()
    existing = db.scalar(select(ProcessingJob).where(ProcessingJob.input_hash == signature))
    if existing and not force:
        return existing
    pending = db.scalar(select(ProcessingJob).where(ProcessingJob.submission_id == submission.id, ProcessingJob.status.in_(('queued', *ACTIVE))))
    if pending: return pending
    midnight = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    if db.scalar(select(func.count()).select_from(ProcessingJob).where(ProcessingJob.requested_by == actor, ProcessingJob.created_at >= midnight)) >= 20:
        raise ValueError('Daily document processing limit (20 jobs) reached.')
    if db.scalar(select(func.count()).select_from(ProcessingJob).where(ProcessingJob.submission_id == submission.id, ProcessingJob.created_at >= midnight)) >= 3:
        raise ValueError('Maximum three analysis versions per submission per day.')
    if force: context['bypass_cache'] = True
    if force: signature = hashlib.sha256((signature + str(uuid4())).encode()).hexdigest()
    job = ProcessingJob(submission_id=submission.id, requested_by=actor, input_hash=signature, content_hash=content_hash, context=context, model=configured_model(), prompt_version=PROMPT_VERSION)
    try:
        with db.begin_nested():
            db.add(job); db.flush()
    except IntegrityError:
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.input_hash == signature))
        if not job: raise
    return job


def claim():
    now = now_utc()
    with SessionLocal() as db:
        if db.bind.dialect.name == 'postgresql':
            db.execute(text('SELECT pg_advisory_xact_lock(62401703)'))
        else:
            db.execute(update(ProcessingJob).where(ProcessingJob.status == 'queued').values(stage=ProcessingJob.stage))
        db.execute(update(ProcessingJob).where(ProcessingJob.status.in_(ACTIVE), ProcessingJob.lease_until < now, ProcessingJob.attempts >= MAX_ATTEMPTS).values(status='failed', stage='failed', error_class='lease_exhausted', error='Worker lease expired after maximum attempts.', updated_at=now))
        busy = db.scalar(select(func.count()).select_from(ProcessingJob).where(ProcessingJob.status.in_(ACTIVE), ProcessingJob.lease_until > now))
        if busy >= limit('FORMA_DOCUMENT_CONCURRENCY',1,2):
            db.commit(); return None
        eligible = (ProcessingJob.attempts < MAX_ATTEMPTS) & (ProcessingJob.available_at <= now) & or_(ProcessingJob.status == 'queued', (ProcessingJob.status.in_(ACTIVE)) & (ProcessingJob.lease_until < now))
        candidate = db.scalar(select(ProcessingJob.id).where(eligible).order_by(ProcessingJob.created_at).limit(1))
        if not candidate:
            db.commit(); return None
        owner = str(uuid4())
        result = db.scalar(update(ProcessingJob).where(ProcessingJob.id == candidate, eligible).values(status='extracting', stage='extracting', attempts=ProcessingJob.attempts+1, lease_owner=owner, lease_until=now+timedelta(minutes=5), updated_at=now).returning(ProcessingJob.id))
        db.commit()
        return (result, owner) if result else None


def process_one():
    claimed = claim()
    if not claimed: return False
    job_id, owner = claimed
    try:
        with SessionLocal() as db:
            job = db.get(ProcessingJob, job_id)
            submission = db.get(AcademicSubmission, job.submission_id)
            structure_row = db.get(SubmissionDocument, job.submission_id)
            structure = structure_row.structure if structure_row else None
            path, file_name, file_type = submission.file_path, submission.file_name, submission.file_type
            context, expected_hash, model = job.context, job.content_hash, job.model
        # Reuse deterministic extraction. Original is fetched only for validation
        # of old records or for bounded PDF page rendering when needed.
        content = read_blob(path)
        if hashlib.sha256(content).hexdigest() != expected_hash:
            raise ValueError('Document content changed after job scheduling.')
        if structure is None:
            structure = ingest(content, file_name, context['document_type']=='programming')
            with SessionLocal() as db:
                if not db.get(SubmissionDocument, job.submission_id):
                    db.add(SubmissionDocument(submission_id=job.submission_id, content_hash=expected_hash, structure=structure)); db.commit()
        if structure['unit_count'] > limit('FORMA_DOCUMENT_JOB_PAGES',50,50):
            raise ProcessingLimitError('Document exceeds processing page/unit limit.')
        with SessionLocal() as db:
            changed = db.scalar(update(ProcessingJob).where(ProcessingJob.id==job_id, ProcessingJob.lease_owner==owner, ProcessingJob.status=='extracting', ProcessingJob.lease_until>now_utc()).values(status='interpreting', stage='interpreting', updated_at=now_utc()).returning(ProcessingJob.id))
            db.commit()
            if not changed: return True
        with SessionLocal() as db:
            cached = db.get(InterpretationCache, context['cache_key']) if not context.get('bypass_cache') else None
            cached_result = cached.result if cached else None
        if cached_result:
            result, usage = cached_result, {'cache_hit':True, 'ai_called':False, 'visual_pages':0}
        else:
            result, usage = gemini_interpret(content, file_type, structure, context['questions'], context['document_type'], model, context['visual_pages'])
        with SessionLocal() as db:
            current = db.scalar(select(ProcessingJob).where(ProcessingJob.id==job_id, ProcessingJob.lease_owner==owner, ProcessingJob.status=='interpreting', ProcessingJob.lease_until>now_utc()).with_for_update())
            if current:
                db.add(DocumentInterpretation(submission_id=current.submission_id, job_id=job_id, result=result))
                if usage.get('ai_called') and not db.get(InterpretationCache, context['cache_key']):
                    try:
                        with db.begin_nested():
                            db.add(InterpretationCache(input_hash=context['cache_key'],result=result)); db.flush()
                    except IntegrityError:
                        pass  # Another bounded worker already published the same cache key.
                current.status='needs_review'; current.stage='review'; current.usage=usage
                current.lease_until=None; current.error=''; current.error_class=''; current.updated_at=now_utc()
                db.commit()
    except Exception as error:
        from google.genai.errors import APIError
        import httpx
        provider_status = getattr(error, 'code', None)
        retryable = not isinstance(error, FileNotFoundError) and isinstance(error, (OSError, TimeoutError, httpx.TransportError)) or (isinstance(error, APIError) and isinstance(provider_status, int) and (provider_status==429 or provider_status>=500))
        classification = 'processing_limit' if isinstance(error, ProcessingLimitError) else 'source_missing' if isinstance(error, FileNotFoundError) else 'provider_temporary' if retryable else 'invalid_document_or_model_output' if isinstance(error, ValueError) else 'processing_error'
        with SessionLocal() as db:
            current=db.scalar(select(ProcessingJob).where(ProcessingJob.id==job_id, ProcessingJob.lease_owner==owner, ProcessingJob.status.in_(ACTIVE), ProcessingJob.lease_until>now_utc()).with_for_update())
            if current:
                current.status='queued' if retryable and current.attempts<MAX_ATTEMPTS else 'failed'
                current.stage=current.status; current.error_class=classification
                current.error='Temporary provider/storage failure; bounded retry scheduled.' if current.status=='queued' else 'Document analysis failed. Check processing limits, document validity and provider configuration; request re-analysis after resolving the cause.'
                if isinstance(error, ProcessingLimitError):
                    current.error='Document exceeds the configured analysis page/unit limit. Manual review remains available.'
                if isinstance(error, FileNotFoundError):
                    current.error='The private original document is unavailable. Restore the source before requesting analysis.'
                current.available_at=now_utc()+timedelta(seconds=15*2**current.attempts)
                current.lease_until=None; current.updated_at=now_utc(); db.commit()
    return True


def start_worker():
    if os.getenv('FORMA_DOCUMENT_WORKER_ENABLED','true').lower() != 'true': return None
    stop=threading.Event()
    def run():
        while not stop.is_set():
            try: worked=process_one()
            except Exception: worked=False
            stop.wait(.2 if worked else 5)
    thread=threading.Thread(target=run,name='forma-document-worker',daemon=True); thread.start()
    return stop,thread
