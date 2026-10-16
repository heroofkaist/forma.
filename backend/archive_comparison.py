"""Resumable local whole-file archive scans. GET only reads saved receipts."""
import hashlib
import json
from fastapi import APIRouter, Request, Response, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from auth import request_user
from accounts import rate_limit, utc
from persistence import SessionLocal, AcademicAssignment, AcademicSubmission, CourseOffering
from document_models import SubmissionDocument
from comparison_models import AssignmentComparison
from services.similarity_vectors import VERSION
from course_archive import source_access, course_ids
from assignment_comparison import prepare_documents, common_payload, baseline_records, run_local, fingerprint

router=APIRouter(prefix='/api/assignment-comparison/archive',tags=['Whole-file course archive'])


def corpus(db, target):
    assignment=db.get(AcademicAssignment,target.assignment_id)
    offering=db.get(CourseOffering,assignment.offering_id)
    courses=sorted(course_ids(db,offering.course_id))
    rows=db.scalars(select(AcademicSubmission).join(AcademicAssignment).join(CourseOffering)
        .where(CourseOffering.course_id.in_(courses),AcademicSubmission.student_id!=target.student_id)
        .order_by(AcademicSubmission.created_at,AcademicSubmission.id)).all()
    sources=[];assignments={}
    for row in [target,*rows]:
        doc=db.get(SubmissionDocument,row.id)
        sources.append([row.id,row.student_id,row.file_name,row.file_type,doc.content_hash if doc else None,hashlib.sha256(json.dumps(doc.structure,sort_keys=True).encode()).hexdigest() if doc else None,
            hashlib.sha256(row.extracted_text.encode()).hexdigest()])
        assignments.setdefault(row.assignment_id,db.get(AcademicAssignment,row.assignment_id))
    bases=baseline_records(db,list(assignments.values()))
    context=[[a.id,a.description,a.questions] for a in assignments.values()]
    key=hashlib.sha256(json.dumps([VERSION,courses,sources,context,
        [[b['id'],b['hash'],b['structure']] for b in bases]],sort_keys=True).encode()).hexdigest()
    return rows,key


def aggregate(db,target,rows,key):
    receipts=db.scalars(select(AssignmentComparison).where(AssignmentComparison.assignment_id==target.assignment_id,
        AssignmentComparison.result['comparison_scope'].as_string()=='archive_files',
        AssignmentComparison.result['target_id'].as_string()==target.id).order_by(AssignmentComparison.created_at.desc())).all()
    current=[r for r in receipts if r.result.get('corpus_key')==key and r.result.get('version')==VERSION]
    done=set();skipped={};pairs={};documents={};limited=False
    for row in reversed(current):
        done.update(row.result['checked_ids']);limited=limited or row.result.get('baseline_limit',False)
        for sid in row.result['checked_ids']: skipped.pop(sid,None)
        skipped.update({s['id']:s['reason'] for s in row.result.get('skipped',[])})
        for pair in row.result['pairs']: pairs[(pair['submission_id'],pair['candidate_id'])]=pair
        for doc in row.result['documents']: documents[doc['id']]=doc
    pending=[r for r in rows if r.id not in done]
    complete=not pending
    partial_count=sum(p['metrics']['document'].get('partial',False) for p in pairs.values())
    state='no_sources' if not rows else 'missing' if not current else 'partial' if pending else 'incomplete' if skipped or partial_count else 'completed'
    ranked=sorted(pairs.values(),key=lambda p:p['metrics']['document'].get('score') if p['metrics']['document'].get('score') is not None else -1,reverse=True)
    # Keep the teacher's report bounded; all batch receipts and coverage persist.
    comparable=sum(p['metrics']['document'].get('score') is not None for p in ranked)
    best=[p for p in ranked if (p['metrics']['document'].get('score') or 0)>0][:20]
    shown={target.id}|{sid for p in best for sid in (p['submission_id'],p['candidate_id'])}
    return {'id':current[0].id if current else None,'status':state,'stale':bool(receipts and not current),'version':VERSION,
        'corpus_key':key,'target_id':target.id,'comparison_scope':'archive_files','pairs':best,
        'documents':[v for k,v in documents.items() if k in shown], 'checked':len(done),'compared':comparable,
        'insufficient_count':len(ranked)-comparable,'partial_count':partial_count,
        'total':len(rows),'remaining':len(pending),'skipped':[{'id':sid,'reason':reason} for sid,reason in skipped.items()],
        'baseline_limit':limited,'created_at':utc(current[0].created_at) if current else None,
        'coverage_complete':complete and not skipped and not partial_count,'scope':'Работы других авторов во всех потоках и связанных курсах этого архива. Предыдущие попытки самого студента исключены.'}


def scan_summary(db, target):
    saved=db.scalar(select(AssignmentComparison.id).where(AssignmentComparison.assignment_id==target.assignment_id,
        AssignmentComparison.result['comparison_scope'].as_string()=='archive_files',AssignmentComparison.result['target_id'].as_string()==target.id).limit(1))
    if not saved: return {'status':'missing','score':None,'candidate_id':None,'checked':0,'total':None,'coverage_complete':False,'stale':False}
    rows,key=corpus(db,target)
    report=aggregate(db,target,rows,key)
    best=next((p for p in report['pairs'] if p['metrics']['document'].get('score') is not None),None)
    metric=best['metrics']['document'] if best else None
    return {'status':report['status'],'score':metric['score'] if metric else 0 if report['compared'] else None,
        'candidate_id':best['candidate_id'] if best and best['submission_id']==target.id else best['submission_id'] if best else None,
        'identical_file':bool(metric and metric.get('identical_file')),'checked':report['checked'],'total':report['total'],
        'coverage_complete':report['coverage_complete'],'stale':report['stale']}


class ScanOptions(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_corpus: str | None = Field(default=None,max_length=64)
    retry_unavailable: bool = False


@router.get('/{sid}')
def get_scan(sid:str,request:Request,response:Response):
    response.headers['Cache-Control']='private, no-store'
    with SessionLocal() as db:
        target,assignment,_=source_access(db,request_user(request),sid)
        rows,key=corpus(db,target)
        return aggregate(db,target,rows,key)


@router.post('/{sid}',status_code=201)
def scan_next(sid:str,payload:ScanOptions,request:Request,response:Response):
    response.headers['Cache-Control']='private, no-store'
    user=request_user(request)
    with SessionLocal() as db:
        target,assignment,_=source_access(db,user,sid)
        rate_limit(request,'archive-file-scan',user.account_id or user.username,120)
        # Serializes same-assignment scans and protects receipt retries. A page
        # reload can resume without recomparing already recorded candidates.
        from review_pilot import lock_assignment
        lock_assignment(db,assignment)
        rows,key=corpus(db,target)
        if payload.expected_corpus and payload.expected_corpus!=key: raise HTTPException(409,'Course archive changed. Reload before continuing the file scan.')
        state=aggregate(db,target,rows,key)
        if not state['remaining'] and not (payload.retry_unavailable and state['skipped']): return state
        done=set()
        for saved in db.scalars(select(AssignmentComparison).where(AssignmentComparison.assignment_id==assignment.id,
                AssignmentComparison.result['target_id'].as_string()==sid,AssignmentComparison.result['comparison_scope'].as_string()=='archive_files')):
            if saved.result.get('corpus_key')==key: done.update(saved.result['checked_ids'])
        retry_ids={s['id'] for s in state['skipped']} if payload.retry_unavailable and not state['remaining'] else set()
        candidate=next(r for r in rows if r.id not in done or r.id in retry_ids)
        source_access(db,user,candidate.id)
        pair_rows=sorted([target,candidate],key=lambda r:r.id)
        pair_key=fingerprint(db,db.get(AcademicAssignment,pair_rows[0].assignment_id),pair_rows,'','archive_pair')
        reusable=db.scalar(select(AssignmentComparison).where(AssignmentComparison.result['pair_key'].as_string()==pair_key)
            .order_by(AssignmentComparison.created_at.desc()).limit(1))
        if reusable and not reusable.result.get('skipped'):
            result={**reusable.result}
        else:
            target_documents=prepare_documents(db,[target],anonymize=True)
            common=common_payload(db,[assignment,db.get(AcademicAssignment,candidate.assignment_id)])
            try:
                documents=[*target_documents,*prepare_documents(db,[candidate],anonymize=True)]
                result=run_local({'documents':documents,'target_id':target.id,**common})
                result.update(skipped=[],baseline_limit=common['baseline_limit'])
            except HTTPException as error:
                # Unavailable input is never a successful zero. No paid calls.
                if error.status_code not in {409,413,422}: raise
                result={'version':VERSION,'pairs':[],'documents':[],'skipped':[{'id':candidate.id,
                    'reason':'Не удалось сопоставить этот файл: проверьте доступность оригиналов, формат и ограничения размера.'}]}
        db.expire_all()
        target,assignment,_=source_access(db,user,sid)
        source_access(db,user,candidate.id)
        refreshed,current_key=corpus(db,target)
        if current_key!=key: raise HTTPException(409,'Course archive changed. Reload before continuing the file scan.')
        result.update(comparison_scope='archive_files',target_id=sid,corpus_key=key,pair_key=pair_key,checked_ids=[candidate.id],
            source_ids=[sid,candidate.id],status='completed')
        receipt=AssignmentComparison(assignment_id=assignment.id,fingerprint=hashlib.sha256((key+candidate.id).encode()).hexdigest(),
            result=result,created_by=user.username)
        db.add(receipt);db.commit()
        return aggregate(db,target,refreshed,key)
