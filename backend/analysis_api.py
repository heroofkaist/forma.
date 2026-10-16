from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from auth import request_user
from accounts import rate_limit, utc
from document_review import get_submission
from document_models import SubmissionDocument
from processing_models import ProcessingJob, DocumentInterpretation, InterpretationCorrection
from institution_models import AuditEvent
from institutions import audit
from persistence import SessionLocal
from document_processing import enqueue, MAX_ATTEMPTS, ACTIVE
from persistence import now_utc
import ai_budget
from services.document_understanding import Interpretation, validate_result

router=APIRouter(prefix='/api/document-analysis',tags=['Document understanding'])

class AnalyzeRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reanalyze: bool=False

class CorrectRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    interpretation_id: str
    result: Interpretation
    confirmed: bool=False


def job_json(job):
    return {'id':job.id,'status':job.status,'stage':job.stage,'attempts':job.attempts,'error':job.error,'error_class':job.error_class,'created_at':utc(job.created_at),'updated_at':utc(job.updated_at),'provider':job.context.get('ai',{}).get('name','gemini'),'partial':bool(job.usage.get('partial')),'model':job.model,'prompt_version':job.prompt_version,'usage':job.usage}


def analysis_questions(assignment, job):
    current = {q['id']:q for q in assignment.questions}
    saved = job.context['questions'] if job else assignment.questions
    return [{**current.get(q['id'],{}),**q,'criteria':current.get(q['id'],q).get('criteria',[])} for q in saved]

@router.post('/{submission_id}',status_code=202)
def analyze(submission_id: str,payload: AnalyzeRequest,request:Request):
    user=request_user(request)
    with SessionLocal() as db:
        submission,assignment=get_submission(db,submission_id,request,teacher=True)
        rate_limit(request,'document-analysis',user.account_id or user.username,10)
        try: job=enqueue(db,submission,assignment,user.account_id or user.username,payload.reanalyze)
        except ValueError as error: raise HTTPException(429,str(error)) from error
        audit(db,user,'document.analysis.request',job.id,{'submission_id':submission_id,'reanalyze':payload.reanalyze})
        db.commit(); return job_json(job)

@router.post('/{submission_id}/resume', status_code=202)
def resume(submission_id: str, request: Request):
    user = request_user(request)
    with SessionLocal() as db:
        get_submission(db, submission_id, request, teacher=True)
        rate_limit(request, 'document-analysis-resume', user.account_id or user.username, 10)
        # Same lock as enqueue: a simultaneous reanalysis must not create a
        # competing active version while this original job is resumed.
        if db.bind.dialect.name == 'postgresql':
            from sqlalchemy import text
            db.execute(text('SELECT pg_advisory_xact_lock(62401704)'))
        else:
            from sqlalchemy import update
            db.execute(update(ProcessingJob).where(ProcessingJob.submission_id == submission_id).values(updated_at=ProcessingJob.updated_at))
        task = func.coalesce(ProcessingJob.context['task'].as_string(), 'understanding')
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.submission_id == submission_id, task == 'understanding').order_by(ProcessingJob.created_at.desc()).limit(1).with_for_update())
        if not job or job.status != 'awaiting_budget' or job.attempts >= MAX_ATTEMPTS:
            raise HTTPException(409, 'No paused job with remaining attempts can be resumed.')
        if job.context.get('ai', {}).get('name') != 'openrouter' or not ai_budget.can_resume(job.id, db=db):
            raise HTTPException(409, 'Paid allowance is not available; reconcile billing or use manual review.')
        active = db.scalar(select(ProcessingJob.id).where(ProcessingJob.submission_id == submission_id, ProcessingJob.status.in_(('queued', *ACTIVE))))
        midnight = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
        requester_jobs = db.scalar(select(func.count()).select_from(ProcessingJob).where(ProcessingJob.requested_by == job.requested_by, ProcessingJob.created_at >= midnight, task != 'integrity'))
        versions = db.scalar(select(func.count()).select_from(ProcessingJob).where(ProcessingJob.submission_id == submission_id, ProcessingJob.created_at >= midnight, task == 'understanding'))
        if active or requester_jobs > 20 or versions > 3:
            raise HTTPException(429, 'Existing job/version limits prevent resuming this analysis.')
        # Attempt history and the safe pause reason are retained until success.
        job.status = 'queued'; job.stage = 'queued'; job.available_at = now_utc(); job.updated_at = now_utc()
        audit(db, user, 'document.analysis.resume', job.id, {'submission_id': submission_id, 'previous_error_class': job.error_class, 'attempts': job.attempts})
        db.commit(); return job_json(job)

@router.get('/{submission_id}/status')
def status(submission_id:str,request:Request):
    with SessionLocal() as db:
        get_submission(db,submission_id,request)
        jobs=db.scalars(select(ProcessingJob).where(ProcessingJob.submission_id==submission_id).order_by(ProcessingJob.created_at.desc())).all()
        visible = [job for job in jobs if job.context.get('task', 'understanding') == 'understanding']
        if request_user(request).role == 'student':
            # Students receive progress, never infrastructure, provider/billing or errors.
            from student_messages import processing_message
            return {'jobs': [{'id': job.id, 'status': job.status, 'error': processing_message(job.status) if job.error else ''}
                             for job in visible], 'worker_note': 'Работа сохранена. Статус обновится после обработки.'}
        return {'jobs': [job_json(job) for job in visible], 'worker_note':'Jobs resume while the backend is awake. Sleeping instances do not process work.'}

@router.get('/{submission_id}')
def interpretation(submission_id:str,request:Request):
    with SessionLocal() as db:
        _, assignment = get_submission(db,submission_id,request,teacher=True)
        rows=db.scalars(select(DocumentInterpretation).where(DocumentInterpretation.submission_id==submission_id).order_by(DocumentInterpretation.created_at.desc())).all()
        items=[]
        for row in rows:
            corrections=db.scalars(select(InterpretationCorrection).where(InterpretationCorrection.interpretation_id==row.id).order_by(InterpretationCorrection.created_at.desc())).all()
            items.append({'id':row.id,'job_id':row.job_id,'original':row.result,'created_at':utc(row.created_at),'corrections':[{'id':correction.id,'result':correction.result,'confirmed':correction.confirmed,'reviewer':correction.reviewer,'created_at':utc(correction.created_at)} for correction in corrections]})
        job = db.get(ProcessingJob, rows[0].job_id) if rows else None
        from services.assignment_context import answer_groups
        questions = analysis_questions(assignment, job)
        return {'items':items,'questions':questions,'answer_groups':answer_groups(questions,assignment.assignment_type)}

@router.post('/{submission_id}/corrections',status_code=201)
def correct(submission_id:str,payload:CorrectRequest,request:Request):
    user=request_user(request)
    with SessionLocal() as db:
        _,assignment=get_submission(db,submission_id,request,teacher=True)
        row=db.get(DocumentInterpretation,payload.interpretation_id)
        if not row or row.submission_id != submission_id: raise HTTPException(404,'Interpretation not found for this submission.')
        structure=db.get(SubmissionDocument,submission_id).structure
        visual=[section['page_number'] for section in row.result['sections'] if section['evidence_kind']=='visual_page']
        try: result=validate_result(payload.result.model_dump(),structure,analysis_questions(assignment,db.get(ProcessingJob,row.job_id)),visual,teacher=True)
        except ValueError as error: raise HTTPException(422,str(error)) from error
        correction=InterpretationCorrection(interpretation_id=row.id,reviewer=user.username,result=result,confirmed=payload.confirmed)
        db.add(correction); db.flush()
        if payload.confirmed:
            job=db.get(ProcessingJob,row.job_id); job.status='completed'; job.stage='completed'
        audit(db,user,'document.interpretation.correct',correction.id,{'interpretation_id':row.id,'confirmed':payload.confirmed})
        db.commit(); return {'id':correction.id,'message':'Interpretation correction saved. No grades were changed.'}
