"""A course archive spans cohorts and verified teachers in the same institution."""
import hashlib
import json
import re
import unicodedata
from urllib.parse import quote
from fastapi import APIRouter, Request, Response, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from auth import request_user
from accounts import utc
from permissions import can_teach, require_teacher
from persistence import SessionLocal, AcademicCourse, AcademicAssignment, AcademicSubmission, CourseOffering, read_blob, now_utc
from account_models import CourseOwner
from institution_models import CourseInstitution
from course_archive_models import CourseArchiveLink, OriginalityCorpusSnapshot
from document_models import SubmissionDocument

router = APIRouter(prefix='/api/course-archive', tags=['Shared course archive'])


def catalogue_key(db, cid):
    alias = db.get(CourseArchiveLink, cid)
    if alias: return alias.archive_key
    owner = db.get(CourseOwner, cid)
    course = db.get(AcademicCourse, cid)
    value = re.sub(r'[^\w]+', '', unicodedata.normalize('NFKC', owner.public_code if owner else course.code).casefold())[:80]
    return value or f'course-{cid}'


def course_ids(db, cid):
    tenant = db.get(CourseInstitution, cid)
    if not tenant: return [cid]
    key = catalogue_key(db, cid)
    return [i for i in db.scalars(select(CourseInstitution.course_id).where(CourseInstitution.institution_id == tenant.institution_id)) if catalogue_key(db, i) == key]


def accessible_courses(db, user):
    result = set()
    for course in db.scalars(select(AcademicCourse)):
        if can_teach(db, user, course.id): result.update(course_ids(db, course.id))
    return result


def source_access(db, user, sid):
    row = db.get(AcademicSubmission, sid)
    assignment = db.get(AcademicAssignment, row.assignment_id) if row else None
    offering = db.get(CourseOffering, assignment.offering_id) if assignment else None
    if not offering: raise HTTPException(404, 'Submission not found.')
    if user.role == 'student' or offering.course_id not in accessible_courses(db, user): raise HTTPException(403, 'This course archive is not available to you.')
    return row, assignment, offering


def corpus_fingerprint(db, submission):
    assignment = db.get(AcademicAssignment, submission.assignment_id)
    offering = db.get(CourseOffering, assignment.offering_id)
    ids = course_ids(db, offering.course_id)
    rows = db.execute(select(AcademicSubmission.id, AcademicSubmission.student_id, AcademicSubmission.extracted_text, AcademicAssignment.family_id)
        .join(AcademicAssignment).join(CourseOffering).where(CourseOffering.course_id.in_(ids))).all()
    sources = [(r.id, r.student_id, r.family_id, hashlib.sha256(r.extracted_text.encode()).hexdigest()) for r in rows]
    return hashlib.sha256(json.dumps([sorted(ids), assignment.originality_enabled, assignment.originality_scope, sorted(sources)]).encode()).hexdigest()


def current_reports(db, sid):
    from persistence import OriginalityReport
    snapshot = db.get(OriginalityCorpusSnapshot, sid)
    query = select(OriginalityReport).where(OriginalityReport.submission_id == sid)
    if snapshot: query = query.where(OriginalityReport.id.in_(snapshot.report_ids))
    return list(db.scalars(query.order_by(OriginalityReport.match_ratio.desc())))


def refresh_similarity(db, submission):
    from persistence import OriginalityAnalysis
    from academic_api import _compare_submission
    receipt = db.get(OriginalityAnalysis, submission.id)
    # A missing/failed/in-flight run must not become a successful zero through a GET.
    if receipt and receipt.status in {'completed', 'no_sources'}:
        snapshot = db.get(OriginalityCorpusSnapshot, submission.id)
        if not snapshot and (not receipt.completed_at or receipt.eligible_token_count < 8):
            return current_reports(db, submission.id)
        if not snapshot or snapshot.fingerprint != corpus_fingerprint(db, submission):
            return _compare_submission(db, submission)
    return current_reports(db, submission.id)


@router.get('/search')
def search(request: Request, response: Response, query: str = '', course_id: str | None = None):
    response.headers['Cache-Control'] = 'private, no-store'
    with SessionLocal() as db:
        user = request_user(request); ids = accessible_courses(db, user)
        if course_id:
            if course_id not in ids: raise HTTPException(403, 'Course archive unavailable.')
            ids = set(course_ids(db, course_id)) & ids
        rows = db.execute(select(AcademicSubmission, AcademicAssignment, CourseOffering, AcademicCourse).select_from(AcademicSubmission)
            .join(AcademicAssignment, AcademicSubmission.assignment_id == AcademicAssignment.id).join(CourseOffering, AcademicAssignment.offering_id == CourseOffering.id).join(AcademicCourse, CourseOffering.course_id == AcademicCourse.id).where(AcademicCourse.id.in_(ids)).order_by(AcademicSubmission.created_at.desc())).all()
        needle = query.strip().casefold(); items = []
        for sub, assignment, offering, course in rows:
            own = can_teach(db, user, course.id)
            name = sub.student_name if own else 'Архивная работа'
            owner = db.get(CourseOwner, course.id)
            code = owner.public_code if owner else course.code
            if needle and needle not in ' '.join([code, course.name, course.instructor, assignment.title, sub.file_name, offering.academic_year, offering.term, name]).casefold(): continue
            items.append({'submission_id': sub.id, 'assignment_id': assignment.id, 'assignment_title': assignment.title,
                'student_name': name, 'student_id': sub.student_id if own else '', 'course_id': course.id,
                'course_code': code, 'course_name': course.name, 'instructor': course.instructor,
                'academic_year': offering.academic_year, 'term': offering.term, 'file_name': sub.file_name,
                'file_type': sub.file_type, 'submitted_at': utc(sub.created_at), 'can_review': own})
        from document_integrity import summaries as integrity_summaries
        from similarity_status import similarity_summaries
        own_ids = {i['submission_id'] for i in items if i['can_review']}
        own_rows = [s for s, *_ in rows if s.id in own_ids]
        integrity = integrity_summaries(db, list(own_ids))
        similarities = similarity_summaries(db, own_rows, refresh=False)
        for item in items:
            item['integrity'] = integrity.get(item['submission_id'])
            item['similarity'] = similarities.get(item['submission_id'])
        return {'items': items}


@router.get('/files/{sid}')
def original(sid: str, request: Request, response: Response):
    response.headers['Cache-Control'] = 'private, no-store'
    with SessionLocal() as db:
        row, _, offering = source_access(db, request_user(request), sid)
        source = db.get(SubmissionDocument, sid)
        own = can_teach(db, request_user(request), offering.course_id)
        return {'submission_id': sid, 'file_name': row.file_name, 'file_type': row.file_type,
            'student_name': row.student_name if own else 'Архивная работа', 'structure': source.structure if source else None, 'can_review': own}


@router.get('/files/{sid}/file')
def download(sid: str, request: Request):
    with SessionLocal() as db:
        row, _, _ = source_access(db, request_user(request), sid)
        try: raw = read_blob(row.file_path)
        except FileNotFoundError as error: raise HTTPException(404, 'Original unavailable.') from error
        return Response(raw, media_type='application/octet-stream', headers={'Cache-Control': 'private, no-store',
            'Content-Disposition': f"attachment; filename*=UTF-8''{quote(row.file_name)}", 'X-Content-Type-Options': 'nosniff'})


@router.get('/files/{sid}/pages/{number}')
def page(sid: str, number: int, request: Request):
    from document_review import render_pdf_page
    with SessionLocal() as db:
        row, _, _ = source_access(db, request_user(request), sid)
        if row.file_type != 'pdf': raise HTTPException(415, 'PDF only.')
        try: raw = read_blob(row.file_path)
        except FileNotFoundError as error: raise HTTPException(404, 'Original unavailable.') from error
    return render_pdf_page(raw, number)


@router.get('/{offering_id}')
def info(offering_id: str, request: Request, response: Response):
    response.headers['Cache-Control'] = 'private, no-store'
    with SessionLocal() as db:
        offering = require_teacher(db, request_user(request), offering_id)
        ids = course_ids(db, offering.course_id); tenant = db.get(CourseInstitution, offering.course_id)
        candidates = db.scalars(select(AcademicCourse).join(CourseInstitution).where(CourseInstitution.institution_id == tenant.institution_id)).all() if tenant else []
        rows = db.execute(select(AcademicSubmission.id).join(AcademicAssignment).join(CourseOffering).where(CourseOffering.course_id.in_(ids))).all()
        return {'course_id': offering.course_id, 'archive_key': catalogue_key(db, offering.course_id), 'course_count': len(ids), 'submission_count': len(rows),
            'courses': [{'id': c.id, 'name': c.name, 'code': db.get(CourseOwner, c.id).public_code if db.get(CourseOwner, c.id) else c.code,
                'instructor': c.instructor, 'linked': c.id in ids} for c in candidates]}


class LinkRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    target_course_id: str = Field(min_length=1, max_length=36)


@router.post('/{offering_id}/link')
def link(offering_id: str, payload: LinkRequest, request: Request):
    from institutions import audit
    with SessionLocal() as db:
        own = require_teacher(db, request_user(request), offering_id)
        first, target = db.get(CourseInstitution, own.course_id), db.get(CourseInstitution, payload.target_course_id)
        if not first or not target or first.institution_id != target.institution_id: raise HTTPException(403, 'Link courses within the same institution.')
        key = catalogue_key(db, payload.target_course_id)
        record = db.get(CourseArchiveLink, own.course_id)
        if record: record.archive_key = key; record.updated_at = now_utc()
        else: db.add(CourseArchiveLink(course_id=own.course_id, archive_key=key))
        audit(db, request_user(request), 'course.archive.link', own.course_id, {'target_course_id': payload.target_course_id})
        db.commit(); return {'linked': True}
