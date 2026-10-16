"""Teacher-only local document checks. No paid model or authorship probability."""
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from accounts import utc, rate_limit
from auth import request_user
from permissions import require_teacher
from persistence import AcademicSubmission, AcademicAssignment, SessionLocal
from processing_models import ProcessingJob
from document_models import SubmissionDocument
from integrity_models import DocumentIntegrityReport
from services.document_integrity import VERSION

router = APIRouter(prefix='/api/document-integrity', tags=['Advisory document analysis'])


def summaries(db, ids):
    if not ids: return {}
    reports = db.scalars(select(DocumentIntegrityReport).where(DocumentIntegrityReport.submission_id.in_(ids))
        .order_by(DocumentIntegrityReport.created_at.desc(), DocumentIntegrityReport.id.desc())).all()
    latest = {}
    for report in reports: latest.setdefault(report.submission_id, report)
    jobs = db.scalars(select(ProcessingJob).where(ProcessingJob.submission_id.in_(ids)).order_by(ProcessingJob.created_at.desc())).all()
    pending = {}
    for job in jobs:
        if job.context.get('task') == 'integrity': pending.setdefault(job.submission_id, job)
    sources = {s.submission_id: s for s in db.scalars(select(SubmissionDocument).where(SubmissionDocument.submission_id.in_(ids)))}
    result = {}
    for sid in ids:
        report, job, source = latest.get(sid), pending.get(sid), sources.get(sid)
        stale = bool(report and (not source or source.content_hash != report.content_hash or report.result.get('version') != VERSION))
        if report and not stale:
            result[sid] = {'id': report.id, 'status': report.result['status'], 'created_at': utc(report.created_at),
                'detector_status': report.result['detector_status'], 'signal_count': len(report.result.get('style_signals', [])),
                'units_analyzed': report.result.get('units_analyzed', 0), 'units_total': report.result.get('units_total', 0),
                'model': report.result.get('model'), 'authorship_probability': None}
        else:
            active = job and source and job.content_hash==source.content_hash and job.prompt_version==VERSION and job.status in {'queued','extracting','interpreting','awaiting_budget','failed'}
            result[sid] = {'status': job.status if active else 'stale' if stale else job.status if job else 'not_analyzed',
                'detector_status': 'not_analyzed', 'authorship_probability': None, 'signal_count': None}
    return result


def enqueue_one(db, submission, assignment, actor, force=False):
    from document_processing import enqueue
    from services.ai_providers.engine import ProviderConfig
    config = ProviderConfig(name='local', model=VERSION, version=VERSION, options={})
    return enqueue(db, submission, assignment, actor, force=force, task_context={'task': 'integrity'}, provider_config=config)


def authorized(db, sid, request):
    row = db.get(AcademicSubmission, sid)
    assignment = db.get(AcademicAssignment, row.assignment_id) if row else None
    if not assignment: raise HTTPException(404, 'Submission not found.')
    require_teacher(db, request_user(request), assignment.offering_id)
    return row, assignment


@router.get('/{sid}')
def get_report(sid: str, request: Request, response: Response):
    response.headers['Cache-Control'] = 'private, no-store'
    with SessionLocal() as db:
        authorized(db, sid, request)
        summary = summaries(db, [sid])[sid]
        if summary.get('id'):
            summary['report'] = db.get(DocumentIntegrityReport, summary['id']).result
        return summary


class RestartRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    force:bool=False


@router.post('/{sid}', status_code=202)
def start_report(sid: str, payload:RestartRequest, request: Request):
    with SessionLocal() as db:
        row, assignment = authorized(db, sid, request)
        rate_limit(request, 'document-integrity', request_user(request).username, 20)
        try: job = enqueue_one(db, row, assignment, request_user(request).username, force=payload.force)
        except (ValueError, RuntimeError) as error: raise HTTPException(409, str(error)) from error
        db.commit()
        return {'id': job.id, 'status': job.status, 'maximum_cost_usd': '0.00', 'provider': 'local'}


@router.post('/assignments/{aid}', status_code=202)
def start_assignment(aid: str, request: Request):
    from assignment_comparison import current_sources
    with SessionLocal() as db:
        assignment = db.get(AcademicAssignment, aid)
        if not assignment: raise HTTPException(404, 'Assignment not found.')
        require_teacher(db, request_user(request), assignment.offering_id)
        rows = current_sources(db, assignment)
        current = summaries(db, [r.id for r in rows])
        eligible = [r for r in rows if current[r.id]['status'] in {'not_analyzed', 'stale', 'awaiting_budget'}]
        jobs = []
        try:
            for row in eligible[:20]: jobs.append(enqueue_one(db, row, assignment, request_user(request).username))
        except (ValueError, RuntimeError) as error:
            if not jobs: raise HTTPException(409, str(error)) from error
        db.commit()
        return {'scheduled': len(jobs), 'remaining': max(0, len(eligible) - len(jobs)),
                'maximum_cost_usd': '0.00', 'provider': 'local'}


@router.post('/{sid}/resume', status_code=202)
def resume_report(sid: str, request: Request):
    # Compatibility for old clients: a paused Qwen detector becomes a local job.
    with SessionLocal() as db:
        row, assignment = authorized(db, sid, request)
        try: job = enqueue_one(db, row, assignment, request_user(request).username)
        except ValueError as error: raise HTTPException(409, str(error)) from error
        db.commit()
        return {'id': job.id, 'status': job.status, 'maximum_cost_usd': '0.00', 'provider': 'local'}
