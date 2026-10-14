import base64
import os
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import ValidationError
from google.genai.errors import APIError
from PIL import UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from schemas import GradingResult
from services.ai_grader import GradingConfigurationError, grade_image
from services.pdf_slicer import NormalizedBox, crop_page, render_preview

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

app = FastAPI(title="AI Grader MVP", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def read_pdf(file: UploadFile) -> bytes:
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=415, detail="Upload a PDF file.")
    content = await file.read()
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
async def pdf_preview(file: Annotated[UploadFile, File()]) -> dict:
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
    file: Annotated[UploadFile, File()],
    page_index: Annotated[int, Form(ge=0)],
    box_json: Annotated[str, Form()],
) -> dict[str, str]:
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
    image: Annotated[UploadFile, File()],
    problem_statement: Annotated[str, Form()],
    reference_solution: Annotated[str, Form()],
    rubric_text: Annotated[str, Form()],
) -> GradingResult:
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

app.include_router(assignment_router)

from academic_api import router as academic_router

app.include_router(academic_router)
