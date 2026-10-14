import hashlib
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from auth import request_user
from accounts import rate_limit, utc
from document_models import CourseMaterial, SubmissionDocument
from permissions import require_student, require_teacher
from persistence import AcademicAssignment, AcademicSubmission, SessionLocal, read_blob, write_blob
from services.document_ingestion import ingest, MAX_BYTES

router = APIRouter(prefix="/api", tags=["Documents and materials"])
MIMES = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}


def access(db, request, offering_id):
    user = request_user(request)
    try:
        require_teacher(db, user, offering_id)
        return "teacher"
    except HTTPException:
        require_student(db, user, offering_id)
        return "student"


def material_json(material):
    return {"id": material.id, "title": material.title, "visibility": material.visibility,
            "tags": material.tags, "file_name": material.file_name, "file_type": material.file_type,
            "status": material.status, "created_at": utc(material.created_at),
            "warnings": material.structure.get("warnings", []), "unit_count": material.structure.get("unit_count")}


@router.get("/course-materials/{offering_id}")
def list_materials(offering_id: str, request: Request):
    with SessionLocal() as db:
        role = access(db, request, offering_id)
        query = select(CourseMaterial).where(CourseMaterial.offering_id == offering_id).order_by(CourseMaterial.created_at.desc())
        if role == "student":
            query = query.where(CourseMaterial.visibility == "student_visible")
        return {"items": [material_json(material) for material in db.scalars(query)]}


@router.post("/course-materials/{offering_id}", status_code=201)
async def upload_material(offering_id: str, request: Request, file: Annotated[UploadFile, File()], title: Annotated[str, Form(min_length=1, max_length=200)], visibility: Annotated[Literal["teacher_only", "student_visible"], Form()] = "teacher_only", tags: Annotated[str, Form(max_length=500)] = ""):
    user = request_user(request)
    with SessionLocal() as db:
        require_teacher(db, user, offering_id)
    rate_limit(request, "material-upload", user.account_id or user.username, 20)
    if not title.strip():
        raise HTTPException(422, "Material title is required.")
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "Document size must not exceed 30 MB.")
    filename = Path(file.filename or "").name[:255]
    try:
        structure = await run_in_threadpool(ingest, content, filename)
    except Exception as exc:
        raise HTTPException(422, str(exc) if isinstance(exc, ValueError) else "Could not read the document.") from exc
    key = f"materials/{offering_id}/{uuid4().hex}.{structure['file_type']}"
    await run_in_threadpool(write_blob, key, content)
    with SessionLocal() as db:
        require_teacher(db, user, offering_id)
        material = CourseMaterial(offering_id=offering_id, title=title.strip(), visibility=visibility, tags=tags, file_path=key, file_name=filename, file_type=structure["file_type"], content_hash=hashlib.sha256(content).hexdigest(), structure=structure)
        db.add(material)
        db.commit()
        return material_json(material)


@router.get("/materials/{material_id}/file")
def material_file(material_id: str, request: Request):
    with SessionLocal() as db:
        material = db.get(CourseMaterial, material_id)
        if not material:
            raise HTTPException(404, "Material not found.")
        role = access(db, request, material.offering_id)
        if role == "student" and material.visibility != "student_visible":
            raise HTTPException(403, "This material is teacher-only.")
        return Response(read_blob(material.file_path), media_type=MIMES[material.file_type], headers={"Content-Disposition": f'attachment; filename="material.{material.file_type}"', "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/submission-documents/{submission_id}")
def submission_document(submission_id: str, request: Request):
    with SessionLocal() as db:
        submission = db.get(AcademicSubmission, submission_id)
        assignment = db.get(AcademicAssignment, submission.assignment_id) if submission else None
        if not assignment:
            raise HTTPException(404, "Submission not found.")
        role = access(db, request, assignment.offering_id)
        if role == "student" and submission.student_id != request_user(request).student_id:
            raise HTTPException(403, "This submission belongs to another student.")
        document = db.get(SubmissionDocument, submission_id)
        if not document:
            raise HTTPException(404, "Structured extraction is unavailable for this historical submission.")
        return document.structure
