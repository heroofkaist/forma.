"""Explicit bounded local analysis. GET never computes or calls an inference provider."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from fastapi import APIRouter, Request, Response, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from accounts import utc, rate_limit
from auth import request_user
from permissions import require_teacher
from persistence import SessionLocal, AcademicAssignment, AcademicSubmission, read_blob
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


def fingerprint(db, assignment, rows, context):
    sources=[]
    for row in rows:
        source=db.get(SubmissionDocument,row.id)
        sources.append((row.id,row.student_id,row.file_name,row.file_type,
            hashlib.sha256(row.extracted_text.encode()).hexdigest(),source.content_hash if source else None,
            hashlib.sha256(json.dumps(source.structure,sort_keys=True).encode()).hexdigest() if source else None))
    return hashlib.sha256(json.dumps({'version':VERSION,'assignment':assignment.id,'instructions':assignment.description,'questions':assignment.questions,'context':context,
        'sources':sources},sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def authorize(db, aid, request, response):
    response.headers['Cache-Control']='private, no-store'
    assignment=db.get(AcademicAssignment,aid)
    if not assignment: raise HTTPException(404,'Assignment not found.')
    require_teacher(db,request_user(request),assignment.offering_id)
    return assignment


def result_json(db, assignment, row):
    stale=row.fingerprint!=fingerprint(db,assignment,current_sources(db,assignment),row.result.get('operator_context',''))
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


@router.get('/{aid}')
def get_comparison(aid:str,request:Request,response:Response):
    with SessionLocal() as db:
        assignment=authorize(db,aid,request,response)
        row=db.scalar(select(AssignmentComparison).where(AssignmentComparison.assignment_id==aid).order_by(AssignmentComparison.created_at.desc(),AssignmentComparison.id.desc()))
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
        documents=[]; total=0
        for row in rows:
            source=db.get(SubmissionDocument,row.id)
            if not source: raise HTTPException(409,'A submission has no extracted structure. Prepare the original before comparing.')
            try: content=read_blob(row.file_path)
            except (FileNotFoundError,OSError) as error: raise HTTPException(409,'An original document is unavailable.') from error
            total+=len(content)
            if len(content)>30*1024*1024 or total>MAX_BYTES:
                raise HTTPException(413,'Local comparison is limited to 60 MB of originals.')
            if hashlib.sha256(content).hexdigest()!=source.content_hash:
                raise HTTPException(409,'An original document changed. Reload the submission before comparing.')
            documents.append({'id':row.id,'student_id':row.student_id,'file_name':row.file_name,'file_type':row.file_type,
                'text':source.structure.get('extracted_text',row.extracted_text),'pages':source.structure.get('pages',[]),'content':base64.b64encode(content).decode()})
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
