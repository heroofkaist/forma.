"""Teacher task sheets inform association only after explicit question approval."""
import re
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from accounts import rate_limit
from auth import request_user
from institutions import audit
from permissions import require_teacher
from persistence import SessionLocal, AcademicAssignment, write_blob
from processing_models import AssignmentBrief
from services.document_ingestion import ingest, MAX_BYTES

router=APIRouter(prefix='/api/assignment-briefs',tags=['Assignment task sheets'])

class BriefQuestion(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:str=Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    title:str=Field(min_length=1,max_length=200)
    statement:str=Field(default='',max_length=10000)

class ApproveQuestions(BaseModel):
    model_config=ConfigDict(extra='forbid')
    brief_id:str=Field(max_length=36)
    questions:list[BriefQuestion]=Field(min_length=1,max_length=100)


def assignment(db,identifier,request):
    row=db.get(AcademicAssignment,identifier)
    if not row:raise HTTPException(404,'Assignment not found.')
    require_teacher(db,request_user(request),row.offering_id)
    return row


def proposals(text):
    headings=list(re.finditer(r'(?im)^\s*(?:question|вопрос|задача)\s*(\d+)\b[^\n]*',text))[:100]
    result=[];seen=set()
    for index,heading in enumerate(headings):
        number=heading.group(1)
        if number in seen:continue
        seen.add(number)
        end=headings[index+1].start() if index+1<len(headings) else len(text)
        result.append({'id':f'brief-q{number}','title':heading.group().strip()[:200],'statement':text[heading.start():end].strip()[:10000]})
    return result

@router.get('/{assignment_id}')
def list_briefs(assignment_id:str,request:Request):
    with SessionLocal() as db:
        assignment(db,assignment_id,request)
        rows=db.scalars(select(AssignmentBrief).where(AssignmentBrief.assignment_id==assignment_id).order_by(AssignmentBrief.created_at.desc())).all()
        return {'items':[{'id':row.id,'file_name':row.file_name,'proposed_questions':row.proposed_questions,'approved_questions':row.approved_questions,'warnings':row.structure.get('warnings',[])} for row in rows]}

@router.post('/{assignment_id}',status_code=201)
async def upload(assignment_id:str,request:Request,file:UploadFile=File(...)):
    user=request_user(request)
    with SessionLocal() as db:assignment(db,assignment_id,request)
    rate_limit(request,'assignment-brief-upload',user.account_id or user.username,20)
    content=await file.read(MAX_BYTES+1)
    if len(content)>MAX_BYTES:raise HTTPException(413,'Assignment brief exceeds 30 MB.')
    name=Path(file.filename or '').name[:255]
    try:structure=await run_in_threadpool(ingest,content,name)
    except Exception as error:raise HTTPException(422,'Could not extract this assignment brief; upload a supported PDF, DOCX or PPTX.') from error
    key=f'assignment-briefs/{assignment_id}/{uuid4().hex}.{structure["file_type"]}'
    await run_in_threadpool(write_blob,key,content)
    with SessionLocal() as db:
        assignment(db,assignment_id,request)
        row=AssignmentBrief(assignment_id=assignment_id,file_path=key,file_name=name,structure=structure,proposed_questions=proposals(structure['extracted_text']))
        db.add(row);db.flush();audit(db,user,'assignment.brief.upload',row.id);db.commit()
        return {'id':row.id,'questions':row.proposed_questions,'warnings':structure['warnings']}

@router.post('/{assignment_id}/approve')
def approve(assignment_id:str,payload:ApproveQuestions,request:Request):
    with SessionLocal() as db:
        assignment(db,assignment_id,request)
        row=db.get(AssignmentBrief,payload.brief_id)
        if not row or row.assignment_id!=assignment_id:raise HTTPException(404,'Brief not found.')
        if len({question.id for question in payload.questions})!=len(payload.questions):raise HTTPException(422,'Question IDs must be unique.')
        row.approved_questions=[question.model_dump() for question in payload.questions]
        audit(db,request_user(request),'assignment.brief.questions.approve',row.id,{'question_count':len(row.approved_questions)})
        db.commit()
    return {'message':'Task questions approved for future interpretation. Grading rubric was not changed.'}
