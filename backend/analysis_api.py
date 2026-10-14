from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from auth import request_user
from accounts import rate_limit, utc
from document_review import get_submission
from document_models import SubmissionDocument
from processing_models import ProcessingJob, DocumentInterpretation, InterpretationCorrection
from institution_models import AuditEvent
from institutions import audit
from persistence import SessionLocal
from document_processing import enqueue
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
    return {'id':job.id,'status':job.status,'stage':job.stage,'attempts':job.attempts,'error':job.error,'error_class':job.error_class,'created_at':utc(job.created_at),'updated_at':utc(job.updated_at),'model':job.model,'prompt_version':job.prompt_version,'usage':job.usage}

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

@router.get('/{submission_id}/status')
def status(submission_id:str,request:Request):
    with SessionLocal() as db:
        get_submission(db,submission_id,request)
        jobs=db.scalars(select(ProcessingJob).where(ProcessingJob.submission_id==submission_id).order_by(ProcessingJob.created_at.desc())).all()
        return {'jobs':[job_json(job) for job in jobs], 'worker_note':'Jobs resume while the backend is awake. Sleeping instances do not process work.'}

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
        return {'items':items,'questions':job.context['questions'] if job else assignment.questions}

@router.post('/{submission_id}/corrections',status_code=201)
def correct(submission_id:str,payload:CorrectRequest,request:Request):
    user=request_user(request)
    with SessionLocal() as db:
        _,assignment=get_submission(db,submission_id,request,teacher=True)
        row=db.get(DocumentInterpretation,payload.interpretation_id)
        if not row or row.submission_id != submission_id: raise HTTPException(404,'Interpretation not found for this submission.')
        structure=db.get(SubmissionDocument,submission_id).structure
        visual=[section['page_number'] for section in row.result['sections'] if section['evidence_kind']=='visual_page']
        try: result=validate_result(payload.result.model_dump(),structure,db.get(ProcessingJob,row.job_id).context['questions'],visual,teacher=True)
        except ValueError as error: raise HTTPException(422,str(error)) from error
        correction=InterpretationCorrection(interpretation_id=row.id,reviewer=user.username,result=result,confirmed=payload.confirmed)
        db.add(correction); db.flush()
        if payload.confirmed:
            job=db.get(ProcessingJob,row.job_id); job.status='completed'; job.stage='completed'
        audit(db,user,'document.interpretation.correct',correction.id,{'interpretation_id':row.id,'confirmed':payload.confirmed})
        db.commit(); return {'id':correction.id,'message':'Interpretation correction saved. No grades were changed.'}
