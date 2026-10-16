import base64
import os
import re
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ConfigDict
from pydantic import ValidationError
from google.genai.errors import APIError
from PIL import UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from schemas import GradingResult
from services.ai_grader import GradingConfigurationError, grade_image
from services.pdf_slicer import NormalizedBox, crop_page, render_preview
from auth import (
    authenticate,
    auth_required,
    create_token,
    request_user,
    validate_auth_configuration,
    verify_token,
)

if os.getenv("FORMA_LOAD_ENV_FILE", "true").lower() == "true":
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

app = FastAPI(title="AI Grader MVP", version="0.1.0")


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(pattern="^(teacher|student)$")
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


@app.on_event("startup")
def validate_auth_settings() -> None:
    validate_auth_configuration()


@app.middleware("http")
async def enforce_api_authentication(request: Request, call_next):
    path = request.url.path
    if path in {"/health", "/api/health", "/api/auth/status", "/api/auth/login",
                "/api/accounts/status", "/api/accounts/register", "/api/accounts/age-check", "/api/accounts/verify-email",
                "/api/accounts/forgot-password", "/api/accounts/reset-password",
                "/api/accounts/resend-verification", "/api/accounts/guardian-consent/request",
                "/api/accounts/guardian-consent/status", "/api/accounts/guardian-consent/inspect",
                "/api/accounts/guardian-consent/decision"}:
        return await call_next(request)

    is_api = path.startswith(("/api/", "/academic/", "/assignments", "/answers"))
    if not is_api or not auth_required():
        return await call_next(request)

    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return JSONResponse(status_code=401, content={"detail": "Bearer authentication required."})
    try:
        user = verify_token(token)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    request.state.auth_user = user
    from permissions import authorize_request
    try:
        await authorize_request(request, user)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    student_routes = (
        path in {"/api/auth/me", "/api/auth/logout"}
        or path.startswith(("/api/accounts/", "/api/institutions", "/api/enrollment/"))
        or (path.startswith("/api/document-analysis/") and path.endswith("/status") and request.method == "GET")
        or (re.fullmatch(r"/api/teaching/submissions/[^/]+/revision", path) is not None and request.method == "GET")
        or (path.startswith(("/api/course-materials/", "/api/materials/", "/api/submission-documents/", "/api/submission-files/")) and request.method == "GET")
        or (path == "/academic/courses" and request.method == "GET")
        or (path == "/academic/enroll" and request.method == "POST")
        or (path.startswith("/academic/student/") and request.method == "GET")
        or (
            re.fullmatch(r"/academic/offerings/[^/]+(?:/assignments)?", path) is not None
            and request.method == "GET"
        )
        or (
            re.fullmatch(r"/academic/assignments/[^/]+/submissions", path) is not None
            and request.method == "POST"
        )
    )
    if user.role == "student" and not student_routes:
        return JSONResponse(status_code=403, content={"detail": "Teacher role required."})
    return await call_next(request)


@app.get("/api/auth/status")
def auth_status() -> dict[str, bool]:
    return {"required": auth_required()}


@app.post("/api/auth/login")
def auth_login(payload: LoginRequest, request: Request) -> dict[str, str | int]:
    if not auth_required():
        raise HTTPException(status_code=409, detail="Authentication is disabled.")
    from accounts import rate_limit
    rate_limit(request, "login", payload.username, 10)
    user = authenticate(payload.role, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return {
        "access_token": create_token(user),
        "token_type": "bearer",
        "expires_in": 8 * 60 * 60,
    }


@app.get("/api/auth/me")
def auth_me(request: Request) -> dict[str, str | None]:
    if not auth_required():
        return {"role": "demo", "username": None, "student_id": None}
    user = request_user(request)
    return {"role": user.role, "username": user.username, "student_id": user.student_id, "account_id": user.account_id}


app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def limit_document_request(request: Request, action: str, maximum: int):
    if auth_required():
        from accounts import rate_limit
        user = request_user(request)
        rate_limit(request, action, user.account_id or user.username, maximum)


async def read_pdf(file: UploadFile) -> bytes:
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=415, detail="Upload a PDF file.")
    content = await file.read(30 * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded PDF is empty.")
    if len(content) > 30 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF size must not exceed 30 MB.")
    return content


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health")
def health_alias() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/pdf/preview")
async def pdf_preview(request: Request, file: Annotated[UploadFile, File()]) -> dict:
    limit_document_request(request, "pdf-preview", 30)
    content = await read_pdf(file)
    try:
        preview = render_preview(content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "page_count": preview.page_count,
        "width": preview.width,
        "height": preview.height,
        "preview_data_url": preview.preview_data_url,
    }


@app.post("/api/pdf/crop")
async def pdf_crop(
    request: Request,
    file: Annotated[UploadFile, File()],
    page_index: Annotated[int, Form(ge=0)],
    box_json: Annotated[str, Form()],
) -> dict[str, str]:
    limit_document_request(request, "pdf-crop", 60)
    content = await read_pdf(file)
    try:
        box = NormalizedBox.model_validate_json(box_json)
        png = crop_page(content, page_index, box)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    encoded = base64.b64encode(png).decode("ascii")
    return {"image_data_url": f"data:image/png;base64,{encoded}"}


@app.post("/api/grade", response_model=GradingResult)
async def grade(
    request: Request,
    image: Annotated[UploadFile, File()],
    problem_statement: Annotated[str, Form()],
    reference_solution: Annotated[str, Form()],
    rubric_text: Annotated[str, Form()],
) -> GradingResult:
    limit_document_request(request, "image-grade", 10)
    if image.content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(status_code=415, detail="Upload a PNG, JPEG, or WebP crop.")
    image_bytes = await image.read(10 * 1024 * 1024 + 1)
    if not image_bytes:
        raise HTTPException(status_code=400, detail="The uploaded crop is empty.")
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image size must not exceed 10 MB.")
    try:
        return await run_in_threadpool(
            grade_image, image_bytes, problem_statement, reference_solution, rubric_text
        )
    except GradingConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail="Gemini returned invalid grading data.") from exc
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=422, detail="The uploaded crop is not a valid image.") from exc
    except APIError as exc:
        raise HTTPException(status_code=502, detail="Gemini grading service failed.") from exc


from assignment_api import router as assignment_router

from assignment_comparison import router as assignment_comparison_router
app.include_router(assignment_comparison_router)
from document_integrity import router as integrity_router
app.include_router(integrity_router)
app.include_router(assignment_router)

from academic_api import router as academic_router

app.include_router(academic_router)

from accounts import router as accounts_router
from courses import router as courses_router
app.include_router(accounts_router)
from guardian_registration import router as guardian_router
app.include_router(guardian_router)
app.include_router(courses_router)

@app.on_event("startup")
def migrate_accounts():
    from persistence import engine
    from migrations import apply_migrations
    apply_migrations(engine)

@app.post("/api/auth/logout")
def legacy_logout(request: Request):
    if auth_required() and request_user(request).account_id:
        from accounts import logout
        return logout(request)
    return {"message": "Signed out. Legacy bearer tokens expire at their original deadline."}

from materials import router as materials_router
app.include_router(materials_router)

from document_review import router as document_review_router
app.include_router(document_review_router)
from review_pilot import router as review_pilot_router
app.include_router(review_pilot_router)


@app.on_event("startup")
def start_account_email_delivery():
    from email_delivery import start_worker
    app.state.email_worker = start_worker()


@app.on_event("shutdown")
def stop_account_email_delivery():
    worker = getattr(app.state, "email_worker", None)
    if worker:
        stop, thread = worker
        stop.set()
        thread.join(timeout=1)

from institutions import router as institutions_router
app.include_router(institutions_router)

from analysis_api import router as analysis_router
app.include_router(analysis_router)
from assessment_api import router as assessment_router
app.include_router(assessment_router)

@app.on_event("startup")
def start_document_processing():
    from document_processing import start_worker
    app.state.document_worker = start_worker()

@app.on_event("shutdown")
def stop_document_processing():
    worker = getattr(app.state, "document_worker", None)
    if worker:
        stop, thread = worker
        stop.set(); thread.join(timeout=1)

from assignment_briefs import router as assignment_briefs_router
app.include_router(assignment_briefs_router)

from course_archive import router as course_archive_router
app.include_router(course_archive_router)

from teaching_workflow import router as teaching_router
app.include_router(teaching_router)
from archive_comparison import router as archive_comparison_router
app.include_router(archive_comparison_router)
