"""Explicit bounded local analysis. GET never computes or calls an inference provider."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from fastapi import APIRouter, Request, Response, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, or_
from accounts import utc, rate_limit
from auth import request_user
from permissions import require_teacher
from persistence import SessionLocal, AcademicAssignment, AcademicSubmission, CourseOffering, read_blob
from document_models import SubmissionDocument
from comparison_models import AssignmentComparison
from services.similarity_vectors import VERSION, MAX_WORKS, MAX_BYTES

router=APIRouter(prefix='/api/assignment-comparison', tags=['Local comparison'])

class Options(BaseModel):
    model_config=ConfigDict(extra='forbid', str_strip_whitespace=True)
    context: str = Field(default='', max_length=20000)


def current_sources(db, assignment):
    rows=db.scalars(select(AcademicSubmission).where(AcademicSubmission.assignment_id==assignment.id)
        .order_by(AcademicSubmission.created_at.desc(),AcademicSubmission.id.desc())).all()
    latest={}
    for row in rows:
        latest.setdefault(row.student_id,row)
    return sorted(latest.values(),key=lambda row:row.id)


def fingerprint(db, assignment, rows, context, scope='assignment'):
    from integrity_models import DocumentIntegrityReport
    sources=[]
    for row in rows:
        source=db.get(SubmissionDocument,row.id)
        sources.append((row.id,row.student_id,row.file_name,row.file_type,
            hashlib.sha256(row.extracted_text.encode()).hexdigest(),source.content_hash if source else None,
            hashlib.sha256(json.dumps(source.structure,sort_keys=True).encode()).hexdigest() if source else None,
            hashlib.sha256(json.dumps([db.get(AcademicAssignment,row.assignment_id).description,db.get(AcademicAssignment,row.assignment_id).questions],sort_keys=True).encode()).hexdigest(),
            db.scalar(select(DocumentIntegrityReport.id).where(DocumentIntegrityReport.submission_id==row.id).order_by(DocumentIntegrityReport.created_at.desc(),DocumentIntegrityReport.id.desc()).limit(1))))
    return hashlib.sha256(json.dumps({'version':VERSION,'scope':scope,'assignment':assignment.id,'instructions':assignment.description,'questions':assignment.questions,'context':context,
        'sources':sources},sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def authorize(db, aid, request, response):
    response.headers['Cache-Control']='private, no-store'
    assignment=db.get(AcademicAssignment,aid)
    if not assignment: raise HTTPException(404,'Assignment not found.')
    require_teacher(db,request_user(request),assignment.offering_id)
    return assignment


def result_json(db, assignment, row):
    scope=row.result.get('comparison_scope','assignment')
    rows=current_sources(db,assignment) if scope=='assignment' else [db.get(AcademicSubmission,sid) for sid in row.result.get('source_ids',[])]
    stale=any(r is None for r in rows) or row.fingerprint!=fingerprint(db,assignment,rows,row.result.get('operator_context',''),scope)
    return {'id':row.id,'created_at':utc(row.created_at),'stale':stale,**row.result}



def run_local(payload):
    worker=Path(__file__).parent/'services'/'similarity_vectors.py'
    try:
        result=subprocess.run([sys.executable,str(worker)],input=json.dumps(payload),capture_output=True,text=True,timeout=30)
        if result.returncode or len(result.stdout)>8*1024*1024:
            raise ValueError('Unsupported or oversized comparison.')
        value=json.loads(result.stdout)
        if value.get('version')!=VERSION or not isinstance(value.get('pairs'),list):
            raise ValueError('Invalid worker receipt.')
        return value
    except (subprocess.TimeoutExpired, ValueError, OSError) as error:
        raise HTTPException(422,'Local comparison failed or exceeded its limits. No result was recorded.') from error


def prepare_documents(db, rows, anonymize=False):
    from integrity_models import DocumentIntegrityReport
    from services.document_integrity import VERSION as PROFILE_VERSION
    documents=[];total=0
    for row in rows:
        source=db.get(SubmissionDocument,row.id)
        if not source: raise HTTPException(409,'A submission has no extracted structure. Prepare the original before comparing.')
        try: content=read_blob(row.file_path)
        except (FileNotFoundError,OSError) as error: raise HTTPException(409,'An original document is unavailable.') from error
        total+=len(content)
        if len(content)>30*1024*1024 or total>MAX_BYTES: raise HTTPException(413,'Comparison is limited to 60 MB of originals.')
        if hashlib.sha256(content).hexdigest()!=source.content_hash: raise HTTPException(409,'An original document changed. Reload before comparing.')
        profile=db.scalar(select(DocumentIntegrityReport).where(DocumentIntegrityReport.submission_id==row.id,DocumentIntegrityReport.content_hash==source.content_hash).order_by(DocumentIntegrityReport.created_at.desc(),DocumentIntegrityReport.id.desc()).limit(1))
        import hmac
        import os
        author = 'archive-' + hmac.new(os.getenv('FORMA_AUTH_SECRET','local-archive').encode(),row.student_id.encode(),'sha256').hexdigest()[:24] if anonymize else row.student_id
        documents.append({'id':row.id,'student_id':author,'file_name':row.file_name,'file_type':row.file_type,
            'text':source.structure.get('extracted_text',row.extracted_text),'pages':source.structure.get('pages',[]),'content':base64.b64encode(content).decode(),
            'semantic_features':profile.result.get('features',[]) if profile and profile.result.get('status')=='completed' and profile.result.get('version')==PROFILE_VERSION else []})
    return documents

class FileOptions(BaseModel):
    model_config=ConfigDict(extra='forbid')
    submission_ids:list[str]=Field(min_length=2,max_length=10)
    context:str=Field(default='',max_length=20000)

@router.post('/files/compare',status_code=201)
def compare_files(payload:FileOptions,request:Request,response:Response):
    response.headers['Cache-Control']='private, no-store'
    with SessionLocal() as db:
        ids=sorted(set(payload.submission_ids))
        if len(ids)<2: raise HTTPException(422,'Choose at least two different files.')
        rows=[];course=None;assignment=None;teacher_context=[]
        for sid in ids:
            row=db.get(AcademicSubmission,sid)
            current=db.get(AcademicAssignment,row.assignment_id) if row else None
            if not current: raise HTTPException(404,'Submission not found.')
            from course_archive import source_access, course_ids
            source_access(db,request_user(request),sid)
            offering=db.get(CourseOffering,current.offering_id)
            if course is not None and offering.course_id not in course_ids(db,course): raise HTTPException(422,'Compare files from the same course archive.')
            course=offering.course_id;assignment=assignment or current;rows.append(row)
            teacher_context.extend([current.description or '',*(q.get('statement','') for q in current.questions)])
        if len({r.student_id for r in rows})<2: raise HTTPException(422,'Compare works by different students.')
        key=fingerprint(db,assignment,rows,payload.context,'selected_files')
        previous=db.scalar(select(AssignmentComparison).where(AssignmentComparison.assignment_id==assignment.id,AssignmentComparison.fingerprint==key))
        if previous:return result_json(db,assignment,previous)
        rate_limit(request,'file-comparison',request_user(request).username,6)
        documents=prepare_documents(db,rows,anonymize=True)
        result=run_local({'documents':documents,'context':'\n'.join([*teacher_context,payload.context])[:20000]})
        db.expire_all()
        for row in rows:
            current=db.get(AcademicAssignment,row.assignment_id)
            source_access(db,request_user(request),row.id)
        if key!=fingerprint(db,assignment,rows,payload.context,'selected_files'):raise HTTPException(409,'Sources changed during comparison.')
        result.update(status='completed',operator_context=payload.context,comparison_scope='selected_files',source_ids=ids)
        receipt=AssignmentComparison(assignment_id=assignment.id,fingerprint=key,result=result,created_by=request_user(request).username)
        db.add(receipt);db.commit();db.refresh(receipt)
        return result_json(db,assignment,receipt)


@router.get('/{aid}')
def get_comparison(aid:str,request:Request,response:Response):
    with SessionLocal() as db:
        assignment=authorize(db,aid,request,response)
        row=db.scalar(select(AssignmentComparison).where(AssignmentComparison.assignment_id==aid,or_(AssignmentComparison.result['comparison_scope'].as_string().is_(None),AssignmentComparison.result['comparison_scope'].as_string()=='assignment')).order_by(AssignmentComparison.created_at.desc(),AssignmentComparison.id.desc()))
        return result_json(db,assignment,row) if row else {'status':'missing','pairs':[],'documents':[],'stale':False}


@router.post('/{aid}',status_code=201)
def compare(aid:str,payload:Options,request:Request,response:Response):
    with SessionLocal() as db:
        assignment=authorize(db,aid,request,response)
        rows=current_sources(db,assignment)
        if not 2<=len(rows)<=MAX_WORKS:
            raise HTTPException(422,'Local comparison requires 2–40 students with submissions.')
        key=fingerprint(db,assignment,rows,payload.context)
        previous=db.scalar(select(AssignmentComparison).where(AssignmentComparison.assignment_id==aid,AssignmentComparison.fingerprint==key))
        if previous: return result_json(db,assignment,previous)
        rate_limit(request,'assignment-comparison',request_user(request).username,6)
        documents=prepare_documents(db,rows)
        context='\n'.join([assignment.description or '',*(q.get('statement','') for q in assignment.questions),payload.context])[:20000]
        result=run_local({'documents':documents,'context':context})
        # A new upload during computation cannot be silently treated as compared.
        db.expire_all()
        assignment=db.get(AcademicAssignment,aid)
        require_teacher(db,request_user(request),assignment.offering_id)
        if key!=fingerprint(db,assignment,current_sources(db,assignment),payload.context):
            raise HTTPException(409,'Submissions changed during comparison. Reload and run again.')
        result.update(status='completed',operator_context=payload.context)
        row=AssignmentComparison(assignment_id=aid,fingerprint=key,result=result,created_by=request_user(request).username)
        db.add(row);db.commit();db.refresh(row)
        return result_json(db,assignment,row)
