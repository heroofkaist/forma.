import csv
import io
import json
import logging
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from persistence import (
    Answer,
    Assignment,
    SessionLocal,
    Submission,
    init_db,
    read_blob,
    save_blob,
    storage_path,
)
from schemas import GradingResult
from services.ai_grader import GradingConfigurationError, grade_image_with_retry
from services.pdf_slicer import NormalizedBox, crop_page, open_pdf, render_page


router = APIRouter()
logger = logging.getLogger(__name__)


def resolve_demo_mode(demo_setting: str | None, api_key: str | None) -> bool:
    if demo_setting is None:
        return not bool(api_key)
    return demo_setting.strip().lower() in {"1", "true", "yes", "on"}


DEMO_MODE = resolve_demo_mode(
    os.getenv("FORMA_DEMO_MODE", os.getenv("DEMO_MODE")),
    os.getenv("GEMINI_API_KEY"),
)
DEMO_ASSIGNMENT_ID = "00000000-0000-4000-8000-000000000001"
MAX_UPLOAD_BYTES = 30 * 1024 * 1024
MAX_PDF_PAGES = 50
MAX_SUBMISSION_FILES = 20
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="forma-grade")
_queue_slots = threading.BoundedSemaphore(20)


class CriterionIn(BaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=80)
    criterion_id: str | None = Field(default=None, min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=1000)
    maximum_points: float = Field(gt=0, le=1000)


class QuestionIn(BaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    label: str | None = Field(default=None, max_length=200)
    statement: str = Field(default="", max_length=10000)
    reference_solution: str = Field(default="", max_length=20000)
    maximum_points: float = Field(gt=0, le=1000)
    criteria: list[CriterionIn] = Field(default_factory=list, max_length=50)
    region: dict[str, Any] | None = None


class AssignmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    subject: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=5000)
    status: str = Field(default="draft", pattern="^(draft|active|completed)$")
    questions: list[QuestionIn] = Field(min_length=2, max_length=3)
    template_rotation: Literal[0, 90, 180, 270] = 0


class AssignmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    subject: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    status: str | None = Field(default=None, pattern="^(draft|active|completed)$")
    questions: list[QuestionIn] | None = Field(default=None, min_length=2, max_length=3)
    template_rotation: Literal[0, 90, 180, 270] | None = None


class TemplateRequest(BaseModel):
    regions: list[dict[str, Any]] = Field(min_length=2, max_length=3)
    rotation: Literal[0, 90, 180, 270] | None = None


class ReviewRequest(BaseModel):
    score: float | None = Field(default=None, ge=0, le=10000)
    points: float | None = Field(default=None, ge=0, le=10000)
    criteria_results: list[dict[str, Any]] | None = None
    transcription: str | None = Field(default=None, max_length=30000)
    feedback: str | None = Field(default=None, max_length=10000)
    teacher_comment: str | None = Field(default=None, max_length=10000)
    approved: bool | None = None
    review_status: str | None = Field(default=None, pattern="^(unreviewed|reviewed|approved|reopened)$")


def _question(question: QuestionIn) -> dict[str, Any]:
    result = question.model_dump()
    result["id"] = result["id"] or f"q-{uuid4().hex[:10]}"
    result["label"] = result["label"] or result["title"]
    seen: set[str] = set()
    criteria = []
    for index, criterion in enumerate(result["criteria"]):
        criterion_id = criterion["criterion_id"] or criterion["id"] or f"{result['id']}-c{index + 1}"
        if criterion_id in seen:
            raise HTTPException(status_code=422, detail="Criterion IDs must be unique within a question.")
        seen.add(criterion_id)
        criteria.append(
            {
                "id": criterion_id,
                "criterion_id": criterion_id,
                "description": criterion["description"],
                "maximum_points": criterion["maximum_points"],
            }
        )
    if criteria and sum(c["maximum_points"] for c in criteria) > result["maximum_points"] + 1e-6:
        raise HTTPException(status_code=422, detail="Criterion maximums cannot exceed the question maximum.")
    if not criteria:
        criterion_id = f"{result['id']}-overall"
        criteria = [{
            "id": criterion_id,
            "criterion_id": criterion_id,
            "description": "Overall correctness",
            "maximum_points": result["maximum_points"],
        }]
    result["criteria"] = criteria
    if result["region"] is not None:
        result["region"] = _region(result["region"], result["id"])
    return result


def _region(value: dict[str, Any], question_id: str | None = None) -> dict[str, Any]:
    try:
        box = NormalizedBox.model_validate(
            {
                "id": str(value.get("id") or question_id or value.get("question_id") or "region"),
                "title": str(value.get("title") or value.get("label") or value.get("question_id") or "Answer"),
                **{key: value[key] for key in ("x1", "y1", "x2", "y2")},
            }
        )
    except (ValidationError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="A region must have normalized x1, y1, x2, y2 coordinates.") from exc
    if box.x1 >= box.x2 or box.y1 >= box.y2:
        raise HTTPException(status_code=422, detail="A region must have positive width and height.")
    page_index = value.get("page_index", 0)
    if not isinstance(page_index, int) or page_index < 0 or page_index >= MAX_PDF_PAGES:
        raise HTTPException(status_code=422, detail="Region page_index must be between 0 and 49.")
    return {**box.model_dump(), "question_id": value.get("question_id") or question_id, "page_index": page_index}


def _assignment_json(db: Session, assignment: Assignment) -> dict[str, Any]:
    answers = db.scalars(select(Answer).where(Answer.assignment_id == assignment.id)).all()
    return {
        "id": assignment.id,
        "title": assignment.title,
        "subject": assignment.subject,
        "description": assignment.description,
        "status": assignment.status,
        "created_at": assignment.created_at.isoformat(),
        "questions": assignment.questions or [],
        "template_regions": assignment.template_regions or [],
        "template_rotation": assignment.template_rotation,
        "template": {
            "rotation": assignment.template_rotation,
            "regions": assignment.template_regions or [],
        },
        "submission_count": len(db.scalars(select(Submission).where(Submission.assignment_id == assignment.id)).all()),
        "answer_count": len(answers),
        "reviewed_count": sum(answer.review_status in {"reviewed", "approved"} for answer in answers),
        "demo_mode": DEMO_MODE,
    }


def _answer_score(answer: Answer) -> float | None:
    return answer.human_score if answer.human_score is not None else answer.suggested_score


def _answer_json(answer: Answer, maximum_points: float | None = None) -> dict[str, Any]:
    metadata = answer.grading_metadata or {}
    grading = {
        "transcribed_latex": answer.transcription,
        "criteria_results": answer.human_criteria_results or answer.criteria_results,
        "total_score": _answer_score(answer),
        "overall_feedback": answer.feedback,
        "teacher_comment": answer.teacher_comment,
        "uncertainty": metadata.get("uncertainty", 0),
        "requires_human_attention": metadata.get("requires_human_attention", False),
        "attention_reasons": metadata.get("attention_reasons", []),
        "transcription_notes": metadata.get("transcription_notes", []),
        "is_demo_output": answer.is_demo,
    }
    return {
        "id": answer.id,
        "anonymous_student_id": answer.anonymous_student_id or "Student 00",
        "question_id": answer.question_id,
        "submission_id": answer.submission_id,
        "page_index": answer.page_index,
        "page_number": answer.page_index + 1,
        "crop_url": f"/answers/{answer.id}/crop" if answer.crop_path else None,
        "source_page_url": f"/answers/{answer.id}/source-page" if answer.has_source_pdf else None,
        "review_status": answer.review_status,
        "status": answer.status,
        "progress": answer.progress,
        "transcription": answer.transcription,
        "ai_result_json": {
            "transcribed_latex": answer.transcription,
            "criteria_results": answer.criteria_results,
            "total_score": answer.suggested_score,
            "overall_feedback": answer.feedback,
            "uncertainty": metadata.get("uncertainty", 0),
            "requires_human_attention": metadata.get("requires_human_attention", False),
            "attention_reasons": metadata.get("attention_reasons", []),
            "transcription_notes": metadata.get("transcription_notes", []),
            "is_demo_output": answer.is_demo,
        } if answer.suggested_score is not None else None,
        "grading": grading if answer.suggested_score is not None or answer.teacher_overridden else None,
        "criteria_results": grading["criteria_results"],
        "suggested_points": answer.suggested_score,
        "points": _answer_score(answer),
        "teacher_comment": answer.teacher_comment,
        "maximum_points": maximum_points,
        "approved": answer.approved,
        "error": answer.error,
        "demo_mode": DEMO_MODE,
        "is_demo_output": answer.is_demo,
        "uncertainty": metadata.get("uncertainty", 0),
        "requires_human_attention": metadata.get("requires_human_attention", False),
        "attention_reasons": metadata.get("attention_reasons", []),
        "transcription_notes": metadata.get("transcription_notes", []),
        "demo_case": metadata.get("demo_case"),
    }


def _assignment_or_404(db: Session, assignment_id: str) -> Assignment:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    return assignment


def _answer_or_404(db: Session, answer_id: str) -> Answer:
    answer = db.get(Answer, answer_id)
    if answer is None:
        raise HTTPException(status_code=404, detail="Answer not found.")
    return answer


def _rubric(question: dict[str, Any]) -> tuple[dict[str, float], str]:
    criteria = question.get("criteria") or [
        {
            "id": f"{question['id']}-overall",
            "criterion_id": f"{question['id']}-overall",
            "description": "Корректность решения",
            "maximum_points": question["maximum_points"],
        }
    ]
    maxima = {str(c.get("criterion_id") or c.get("id")): float(c["maximum_points"]) for c in criteria}
    text = "\n".join(
        f"- {cid}: {criterion['description']} (максимум {maxima[cid]} баллов)"
        for cid, criterion in zip(maxima, criteria)
    )
    return maxima, text


def validate_grading(result: GradingResult, question: dict[str, Any]) -> dict[str, Any]:
    """Reject unknown/duplicate rubric IDs and calculate the total from bounded criterion scores."""
    maxima, _ = _rubric(question)
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in result.criteria_results:
        criterion_id = item.criterion_id
        if criterion_id not in maxima or criterion_id in seen:
            raise ValueError("Grader returned an unknown or duplicate criterion ID.")
        if item.points_awarded > maxima[criterion_id]:
            raise ValueError("Grader awarded more than a criterion's maximum.")
        if item.status not in {"awarded", "not_awarded", "uncertain"}:
            raise ValueError("Invalid criterion status.")
        seen.add(criterion_id)
        results.append(
            {
                "criterion_id": criterion_id,
                "status": item.status,
                "passed": item.passed,
                "points_awarded": item.points_awarded,
                "comment": item.comment,
                "evidence": item.evidence,
            }
        )
    if seen != set(maxima):
        raise ValueError("Grader did not return exactly the rubric criteria.")
    total = round(sum(item["points_awarded"] for item in results), 4)
    return {
        "transcribed_latex": result.transcribed_latex,
        "criteria_results": results,
        "total_score": total,
        "overall_feedback": result.overall_feedback,
        "uncertainty": result.uncertainty,
        "requires_human_attention": result.requires_human_attention,
        "attention_reasons": result.attention_reasons,
        "transcription_notes": result.transcription_notes,
    }


def _run_grading(assignment_id: str, answer_ids: list[str]) -> None:
    try:
        for answer_id in answer_ids:
            db = SessionLocal()
            try:
                answer = db.get(Answer, answer_id)
                assignment = db.get(Assignment, assignment_id)
                if answer is None or assignment is None or answer.teacher_overridden or answer.approved:
                    continue
                answer.status, answer.progress = "grading", 20
                db.commit()
                question = next((q for q in assignment.questions if q["id"] == answer.question_id), None)
                if question is None:
                    raise ValueError("Question rubric is missing.")
                _, rubric = _rubric(question)
                if DEMO_MODE:
                    maxima, _ = _rubric(question)
                    result = GradingResult(
                        transcribed_latex="Демонстрационный результат (решение не оценивалось).",
                        criteria_results=[
                            {
                                "criterion_id": criterion_id,
                                "status": "uncertain",
                                "passed": False,
                                "points_awarded": 0,
                                "comment": "Демо-оценка: результат сгенерирован автоматически и не является проверкой.",
                                "evidence": [],
                            }
                            for criterion_id, maximum in maxima.items()
                        ],
                        total_score=0,
                        overall_feedback="ДЕМО: Это синтетический пример, а не реальная оценка.",
                        uncertainty=1,
                        requires_human_attention=True,
                        attention_reasons=["Результат создан в демонстрационном режиме и требует реальной проверки."],
                        transcription_notes=["Синтетический результат; не является транскрипцией ответа ученика."],
                    )
                else:
                    result = grade_image_with_retry(
                        read_blob(answer.crop_path),
                        question["statement"],
                        question["reference_solution"],
                        rubric,
                    )
                validated = validate_grading(result, question)
                answer.transcription = validated["transcribed_latex"]
                answer.criteria_results = validated["criteria_results"]
                answer.suggested_score = validated["total_score"]
                answer.feedback = validated["overall_feedback"]
                answer.grading_metadata = {
                    "uncertainty": validated["uncertainty"],
                    "requires_human_attention": validated["requires_human_attention"],
                    "attention_reasons": validated["attention_reasons"],
                    "transcription_notes": validated["transcription_notes"],
                }
                answer.is_demo = DEMO_MODE
                answer.status = "completed"
                answer.progress = 100
                answer.review_status = "unreviewed"
                answer.error = None
            except Exception as exc:
                logger.exception("Grading failed for answer %s", answer_id)
                if answer is not None and not answer.teacher_overridden:
                    answer.status, answer.progress = "failed", 100
                    answer.error = (
                        "GEMINI_API_KEY is not configured. Add it to the backend environment."
                        if isinstance(exc, GradingConfigurationError)
                        else "Grading failed. Retry or check the server configuration."
                    )
            finally:
                db.commit()
                db.close()
    finally:
        _queue_slots.release()


def _demo_seed(db: Session) -> None:
    existing = db.get(Assignment, DEMO_ASSIGNMENT_ID)
    if existing is not None:
        existing_answers = db.scalars(
            select(Answer).where(Answer.assignment_id == DEMO_ASSIGNMENT_ID)
        ).all()
        current_version = bool(existing_answers) and all(
            answer.is_demo
            and not answer.approved
            and not answer.teacher_overridden
            and answer.review_status == "unreviewed"
            and (answer.grading_metadata or {}).get("demo_version") == 2
            for answer in existing_answers
        )
        if current_version:
            return
        safe_to_refresh = bool(existing_answers) and all(
            answer.is_demo
            and not answer.approved
            and not answer.teacher_overridden
            and answer.review_status == "unreviewed"
            for answer in existing_answers
        )
        if not safe_to_refresh:
            return
        db.execute(delete(Answer).where(Answer.assignment_id == DEMO_ASSIGNMENT_ID))
        db.execute(delete(Submission).where(Submission.assignment_id == DEMO_ASSIGNMENT_ID))
        db.delete(existing)
        db.flush()
        demo_storage = storage_path(DEMO_ASSIGNMENT_ID)
        if demo_storage.exists():
            shutil.rmtree(demo_storage)
    regions = [
        {
            "id": "q-components",
            "title": "Force components",
            "question_id": "q-components",
            "x1": 0.03,
            "y1": 0.10,
            "x2": 0.97,
            "y2": 0.43,
            "page_index": 0,
        },
        {
            "id": "q-acceleration",
            "title": "Acceleration",
            "question_id": "q-acceleration",
            "x1": 0.03,
            "y1": 0.35,
            "x2": 0.97,
            "y2": 0.70,
            "page_index": 0,
        },
        {
            "id": "q-normal",
            "title": "Normal force",
            "question_id": "q-normal",
            "x1": 0.03,
            "y1": 0.58,
            "x2": 0.97,
            "y2": 0.95,
            "page_index": 0,
        },
    ]
    assignment = Assignment(
        id=DEMO_ASSIGNMENT_ID,
        title="Тело на наклонной плоскости",
        subject="Физика",
        description=(
            "Демонстрационная задача: брусок массой 2 кг скользит по гладкой "
            "плоскости с углом наклона 30°. Примите g = 10 м/с²."
        ),
        status="active",
        template_regions=regions,
        questions=[
            {
                "id": "q-components",
                "title": "Компоненты силы тяжести",
                "label": "Разложение сил",
                "statement": (
                    "Для бруска массой 2 кг на гладкой плоскости под углом 30° "
                    "к горизонту разложите силу тяжести на компоненты вдоль и "
                    "перпендикулярно плоскости."
                ),
                "reference_solution": "F_parallel = mg sin(30°) = 10 N; F_perpendicular = mg cos(30°) = 10√3 N ≈ 17.3 N.",
                "maximum_points": 2,
                "region": regions[0],
                "criteria": [{
                    "id": "C1", "criterion_id": "C1",
                    "description": "Разложение веса на mg·sin(θ) вдоль и mg·cos(θ) перпендикулярно плоскости.",
                    "maximum_points": 2,
                }],
            },
            {
                "id": "q-acceleration",
                "title": "Ускорение бруска",
                "label": "Уравнение движения",
                "statement": "Найдите ускорение бруска массой 2 кг на гладкой плоскости под углом 30°, если g = 10 м/с².",
                "reference_solution": "mg sin(30°) = ma, поэтому a = g sin(30°) = 5 м/с².",
                "maximum_points": 2,
                "region": regions[1],
                "criteria": [{
                    "id": "C2", "criterion_id": "C2",
                    "description": "Верное уравнение движения вдоль плоскости и ускорение 5 м/с².",
                    "maximum_points": 2,
                }],
            },
            {
                "id": "q-normal",
                "title": "Реакция опоры",
                "label": "Нормальная сила",
                "statement": "Найдите силу нормальной реакции опоры для бруска массой 2 кг на плоскости под углом 30°, если g = 10 м/с².",
                "reference_solution": "N = mg cos(30°) = 10√3 N ≈ 17.3 N.",
                "maximum_points": 1,
                "region": regions[2],
                "criteria": [{
                    "id": "C3", "criterion_id": "C3",
                    "description": "Реакция опоры N = mg·cos(θ) = 10√3 Н (примерно 17,3 Н).",
                    "maximum_points": 1,
                }],
            }
        ],
    )
    db.add(assignment)
    db.flush()
    examples = [
        {
            "case": "correct",
            "label": "Correct solution",
            "writing": [
                "m=2 kg, theta=30 deg, g=10",
                "F_parallel=mg sin(theta)=10 N",
                "a=F/m=5 m/s^2",
                "N=mg cos(theta)=10sqrt(3)=17.3 N",
            ],
            "points": 5,
            "criteria": [
                (2, "Правильно разложена сила тяжести на компоненты вдоль и перпендикулярно плоскости.", ["mg sin(30)=10 Н вдоль плоскости", "mg cos(30) перпендикулярно плоскости"], "awarded"),
                (2, "По второму закону Ньютона получено a=5 м/с².", ["10 Н / 2 кг = 5 м/с²"], "awarded"),
                (1, "Реакция опоры найдена верно: примерно 17,3 Н.", ["N=20 cos(30)=17,3 Н"], "awarded"),
            ],
            "uncertainty": 0.03,
            "needs_attention": False,
            "reasons": [],
            "notes": ["Демонстрационный пример; решение читается."],
            "feedback": "Проекции сил и обе искомые величины найдены верно.",
        },
        {
            "case": "incorrect_decomposition",
            "label": "Incorrect force decomposition",
            "writing": [
                "F along = mg cos(30) = 17.3 N",
                "N = mg sin(30) = 10 N",
                "a = 17.3 / 2 = 8.65 m/s^2",
            ],
            "points": 0,
            "criteria": [
                (0, "Синус и косинус в проекциях перепутаны местами.", ["Вдоль плоскости указано mg cos(θ)", "Для реакции опоры указано mg sin(θ)"], "not_awarded"),
                (0, "Ускорение вычислено из неверной проекции силы.", ["a=8,65 м/с² получено из перепутанной проекции"], "not_awarded"),
                (0, "Для реакции опоры взята неверная перпендикулярная проекция.", ["N=10 Н вместо mg cos(30)"], "not_awarded"),
            ],
            "uncertainty": 0.12,
            "needs_attention": False,
            "reasons": [],
            "notes": ["Демонстрационный пример: синус и косинус в проекциях перепутаны."],
            "feedback": "Проверьте, какая составляющая силы тяжести направлена вдоль плоскости, а какая — перпендикулярно ей.",
        },
        {
            "case": "arithmetic_error",
            "label": "Arithmetic error",
            "writing": [
                "F parallel=mg sin(30)=10 N",
                "a=F/m=10/2=4 m/s^2",
                "N=mg cos(30)=17.3 N",
            ],
            "points": 4,
            "criteria": [
                (2, "Сила тяжести разложена правильно.", ["mg sin(30)=10 Н", "mg cos(30) направлена перпендикулярно"], "awarded"),
                (1, "Ход решения верный, но частное 10/2 вычислено с ошибкой.", ["Записано 10/2=4 м/с²; верное значение — 5 м/с²"], "uncertain"),
                (1, "Реакция опоры найдена верно.", ["N=17,3 Н"], "awarded"),
            ],
            "uncertainty": 0.32,
            "needs_attention": True,
            "reasons": ["Проверьте частичный балл за арифметическую ошибку при вычислении ускорения."],
            "notes": ["В записи деления, вероятно, указано 10/2=4."],
            "feedback": "Физическая модель выбрана верно; проверьте деление при вычислении ускорения.",
        },
        {
            "case": "partially_unreadable",
            "label": "Partially unreadable work",
            "writing": [
                "F_parallel = mg sin(?) = ...",
                "[handwriting obscured]",
                "a = ? m/s^2",
                "N = [unclear]",
            ],
            "points": 2,
            "criteria": [
                (2, "Связь для проекции силы читается и записана верно.", ["Видно: F вдоль = mg sin(...)", "Угол и подстановка неразборчивы"], "awarded"),
                (0, "Ускорение нельзя проверить из-за частично неразборчивой записи.", ["Итоговое ускорение и вычисления не читаются"], "uncertain"),
                (0, "Значение реакции опоры неразборчиво.", ["Строка с реакцией опоры закрыта"], "uncertain"),
            ],
            "uncertainty": 0.88,
            "needs_attention": True,
            "reasons": ["Вычисление ускорения неразборчиво.", "Вычисление реакции опоры неразборчиво."],
            "notes": ["Надёжно расшифрована только начальная запись проекции силы; остальные фрагменты неразборчивы."],
            "feedback": "Проверьте неразборчивые строки с ускорением и реакцией опоры.",
        },
    ]
    for student_number, example in enumerate(examples, start=1):
        pseudonym = f"Student {student_number:02d}"
        submission = Submission(
            assignment_id=assignment.id,
            student_name=pseudonym,
            anonymous_student_id=pseudonym,
            source_path="", page_count=1, status="ready",
        )
        db.add(submission)
        db.flush()
        image = Image.new("RGB", (1100, 560), "white")
        draw = ImageDraw.Draw(image)
        draw.text((35, 25), "ДЕМО-ОБРАЗЕЦ · НАКЛОННАЯ ПЛОСКОСТЬ", fill="gray")
        y = 90
        for line in example["writing"]:
            if line == "[handwriting obscured]":
                for offset in range(5):
                    draw.line((45, y + offset * 8, 700, y + offset * 8 + 45), fill="black", width=3)
            else:
                draw.text((45, y), line, fill="black")
            y += 75
        out = io.BytesIO()
        image.save(out, format="PNG")
        criteria_results = [
            {
                "criterion_id": f"C{index}",
                "status": status,
                "passed": status == "awarded",
                "points_awarded": points,
                "comment": comment,
                "evidence": evidence,
            }
            for index, (points, comment, evidence, status) in enumerate(example["criteria"], 1)
        ]
        for question_index, question in enumerate(assignment.questions):
            question_region = regions[question_index]
            crop = image.crop(
                (
                    round(question_region["x1"] * image.width),
                    round(question_region["y1"] * image.height),
                    round(question_region["x2"] * image.width),
                    round(question_region["y2"] * image.height),
                )
            )
            crop_bytes = io.BytesIO()
            crop.save(crop_bytes, format="PNG")
            crop_path = save_blob(assignment.id, "crops", crop_bytes.getvalue(), ".png")
            points, _, _, _ = example["criteria"][question_index]
            db.add(
                Answer(
                assignment_id=assignment.id,
                submission_id=submission.id,
                question_id=question["id"],
                anonymous_student_id=pseudonym,
                crop_path=crop_path, page_index=0, status="completed", progress=100,
                suggested_score=points,
                transcription="\n".join(example["writing"]),
                is_demo=True,
                criteria_results=[criteria_results[question_index]],
                grading_metadata={
                    "demo_version": 2,
                    "uncertainty": example["uncertainty"],
                    "requires_human_attention": example["needs_attention"],
                    "attention_reasons": example["reasons"],
                    "transcription_notes": example["notes"],
                    "demo_case": example["case"],
                },
                feedback=f"ДЕМО: {example['feedback']}",
                review_status="unreviewed",
                )
            )
    db.commit()


@router.on_event("startup")
def startup() -> None:
    init_db()
    if DEMO_MODE:
        with SessionLocal() as db:
            _demo_seed(db)


@router.get("/assignments")
def list_assignments() -> dict[str, Any]:
    with SessionLocal() as db:
        items = db.scalars(select(Assignment).order_by(Assignment.created_at.desc())).all()
        return {"items": [_assignment_json(db, item) for item in items], "demo_mode": DEMO_MODE}


@router.post("/assignments", status_code=201)
def create_assignment(payload: AssignmentCreate) -> dict[str, Any]:
    with SessionLocal() as db:
        assignment = Assignment(
            title=payload.title, subject=payload.subject, description=payload.description,
            status=payload.status, questions=[_question(q) for q in payload.questions],
            template_rotation=payload.template_rotation,
        )
        db.add(assignment)
        db.commit()
        db.refresh(assignment)
        return _assignment_json(db, assignment)


@router.get("/assignments/{assignment_id}")
def get_assignment(assignment_id: str) -> dict[str, Any]:
    with SessionLocal() as db:
        return _assignment_json(db, _assignment_or_404(db, assignment_id))


@router.put("/assignments/{assignment_id}")
def update_assignment(assignment_id: str, payload: AssignmentCreate) -> dict[str, Any]:
    with SessionLocal() as db:
        assignment = _assignment_or_404(db, assignment_id)
        assignment.title = payload.title
        assignment.subject = payload.subject
        assignment.description = payload.description
        assignment.status = payload.status
        assignment.questions = [_question(question) for question in payload.questions]
        assignment.template_rotation = payload.template_rotation
        db.commit()
        db.refresh(assignment)
        return _assignment_json(db, assignment)


@router.patch("/assignments/{assignment_id}")
def patch_assignment(assignment_id: str, payload: AssignmentUpdate) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    with SessionLocal() as db:
        assignment = _assignment_or_404(db, assignment_id)
        for field in ("title", "subject", "description", "status", "template_rotation"):
            if field in changes and changes[field] is not None:
                setattr(assignment, field, changes[field])
        if "questions" in changes:
            assignment.questions = [_question(question) for question in payload.questions or []]
        db.commit()
        db.refresh(assignment)
        return _assignment_json(db, assignment)


@router.delete("/assignments/{assignment_id}", status_code=204)
def delete_assignment(assignment_id: str) -> Response:
    with SessionLocal() as db:
        assignment = _assignment_or_404(db, assignment_id)
        db.execute(delete(Answer).where(Answer.assignment_id == assignment_id))
        db.execute(delete(Submission).where(Submission.assignment_id == assignment_id))
        db.delete(assignment)
        db.commit()
    folder = storage_path(assignment_id)
    if folder.exists():
        shutil.rmtree(folder)
    return Response(status_code=204)


@router.post("/assignments/{assignment_id}/template")
def save_template(assignment_id: str, payload: TemplateRequest) -> dict[str, Any]:
    with SessionLocal() as db:
        assignment = _assignment_or_404(db, assignment_id)
        if not 2 <= len(assignment.questions or []) <= 3:
            raise HTTPException(status_code=409, detail="Assignments must have 2 or 3 questions before saving a template.")
        regions = [_region(region, region.get("question_id")) for region in payload.regions]
        if payload.rotation is not None:
            assignment.template_rotation = payload.rotation
        unknown = {r["question_id"] for r in regions if r["question_id"]} - {q["id"] for q in assignment.questions}
        if unknown:
            raise HTTPException(status_code=422, detail="Template region references an unknown question.")
        assignment.template_regions = regions
        questions = {q["id"]: q for q in assignment.questions}
        for region in regions:
            if region["question_id"]:
                questions[region["question_id"]]["region"] = region
        assignment.questions = list(questions.values())
        db.commit()
        db.refresh(assignment)
        return _assignment_json(db, assignment)


@router.post("/assignments/{assignment_id}/submissions", status_code=201)
async def create_submissions(
    assignment_id: str,
    file: UploadFile | None = File(default=None),
    files: list[UploadFile] | None = File(default=None),
    student_name: str = Form(default=""),
    template_regions: str | None = Form(default=None),
    config: str | None = Form(default=None),
) -> dict[str, Any]:
    uploads = (files or []) + ([file] if file else [])
    if not uploads or len(uploads) > MAX_SUBMISSION_FILES:
        raise HTTPException(status_code=400, detail=f"Upload between 1 and {MAX_SUBMISSION_FILES} PDFs.")
    with SessionLocal() as db:
        assignment = _assignment_or_404(db, assignment_id)
        regions = assignment.template_regions or []
        supplied = template_regions or config
        if supplied:
            try:
                value = json.loads(supplied)
                if isinstance(value, dict):
                    region_list = value.get("regions", value.get("template_regions"))
                    value = region_list if region_list is not None else [
                        {"question_id": question_id, **region}
                        for question_id, region in value.items()
                        if isinstance(region, dict) and {"x1", "y1", "x2", "y2"} <= region.keys()
                    ]
                regions = [_region(region, region.get("question_id")) for region in value]
            except (ValueError, TypeError) as exc:
                raise HTTPException(status_code=422, detail="template_regions/config must be a JSON array of regions.") from exc
        q_by_id = {q["id"]: q for q in assignment.questions}
        if not regions:
            regions = [q["region"] for q in assignment.questions if q.get("region")]
        if not regions:
            raise HTTPException(status_code=409, detail="Save template regions before uploading submissions.")
        if not 2 <= len(regions) <= 3:
            raise HTTPException(status_code=422, detail="Provide template regions for 2 to 3 questions.")
        region_question_ids = [r.get("question_id") or r.get("id") for r in regions]
        if len(set(region_question_ids)) != len(region_question_ids):
            raise HTTPException(status_code=422, detail="Each template region must reference a different question.")
        unknown_question_ids = set(region_question_ids) - q_by_id.keys()
        if unknown_question_ids:
            raise HTTPException(status_code=422, detail="A submission region references an unknown question.")
        inserted: list[Answer] = []
        submissions: list[Submission] = []
        next_student_number = len(
            db.scalars(select(Submission.id).where(Submission.assignment_id == assignment_id)).all()
        ) + 1
        student_number = next_student_number
        for upload in uploads:
            if upload.content_type != "application/pdf":
                raise HTTPException(status_code=415, detail="Upload PDF submissions only.")
            content = await upload.read(MAX_UPLOAD_BYTES + 1)
            if len(content) > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="PDF size must not exceed 30 MB.")
            if not content:
                raise HTTPException(status_code=400, detail="An uploaded PDF is empty.")
            try:
                document = open_pdf(content)
                page_count = document.page_count
                document.close()
                if page_count > MAX_PDF_PAGES:
                    raise HTTPException(status_code=413, detail="PDFs may contain at most 50 pages.")
                source_path = save_blob(assignment.id, "sources", content, ".pdf")
                for page_index in range(page_count):
                    pseudonym = f"Student {student_number:02d}"
                    student_number += 1
                    submission = Submission(
                        assignment_id=assignment.id,
                        student_name=pseudonym,
                        anonymous_student_id=pseudonym,
                        source_path=source_path,
                        page_count=page_count,
                    )
                    db.add(submission)
                    db.flush()
                    submissions.append(submission)
                    for region_data in regions:
                        question_id = region_data.get("question_id") or region_data.get("id")
                        question = q_by_id[question_id]
                        try:
                            region = _region(region_data, question_id)
                            region["page_index"] = page_index
                            box = NormalizedBox.model_validate(region)
                            png = crop_page(content, page_index, box, assignment.template_rotation)
                            crop_path = save_blob(assignment.id, "crops", png, ".png")
                            answer = Answer(
                                assignment_id=assignment.id,
                                submission_id=submission.id,
                                question_id=question_id,
                                crop_path=crop_path,
                                page_index=page_index,
                                anonymous_student_id=pseudonym,
                                has_source_pdf=True,
                            )
                        except (ValueError, ValidationError, OSError, RuntimeError) as exc:
                            answer = Answer(
                                assignment_id=assignment.id,
                                submission_id=submission.id,
                                question_id=question_id,
                                anonymous_student_id=pseudonym,
                                crop_path="",
                                page_index=page_index,
                                status="failed",
                                progress=100,
                                has_source_pdf=True,
                                error=f"Crop generation failed ({exc}). Adjust the region and use retry-crop.",
                            )
                        db.add(answer)
                        inserted.append(answer)
            except HTTPException:
                raise
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        db.commit()
        for answer in inserted:
            db.refresh(answer)
        return {
            "submissions": [
                {
                    "id": item.id,
                    "anonymous_student_id": item.anonymous_student_id,
                    "page_count": item.page_count,
                }
                for item in submissions
            ],
            "answers": [
                _answer_json(answer, q_by_id[answer.question_id]["maximum_points"])
                for answer in inserted
            ],
            "submission_count": len(submissions),
            "answer_count": len(inserted),
            "demo_mode": DEMO_MODE,
        }


@router.post("/assignments/{assignment_id}/grade", status_code=202)
def start_grading(assignment_id: str) -> dict[str, Any]:
    with SessionLocal() as db:
        assignment = _assignment_or_404(db, assignment_id)
        pending = db.scalars(
            select(Answer).where(
                Answer.assignment_id == assignment_id,
                Answer.status.in_(["pending", "failed"]),
                Answer.teacher_overridden.is_(False),
                Answer.approved.is_(False),
                Answer.crop_path != "",
            )
        ).all()
        ids = [answer.id for answer in pending]
        if not ids:
            return {"assignment_id": assignment.id, "status": "completed", "queued": 0, "demo_mode": DEMO_MODE}
        if not _queue_slots.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="Grading queue is full; retry later.")
        for answer in pending:
            answer.status, answer.progress, answer.error = "queued", 0, None
        db.commit()
    _executor.submit(_run_grading, assignment_id, ids)
    return {"assignment_id": assignment_id, "status": "queued", "queued": len(ids), "demo_mode": DEMO_MODE}


@router.post("/answers/{answer_id}/retry", status_code=202)
def retry_answer(answer_id: str) -> dict[str, Any]:
    with SessionLocal() as db:
        answer = _answer_or_404(db, answer_id)
        if answer.approved or answer.teacher_overridden:
            raise HTTPException(status_code=409, detail="Approved or teacher-overridden grades cannot be retried.")
        if answer.status not in {"pending", "failed"}:
            raise HTTPException(status_code=409, detail="Only pending or failed answers can be retried.")
        if not answer.crop_path:
            raise HTTPException(status_code=409, detail="Regenerate the answer crop before retrying grading.")
        if not _queue_slots.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="Grading queue is full; retry later.")
        assignment_id = answer.assignment_id
        answer.status, answer.progress, answer.error = "queued", 0, None
        db.commit()
    try:
        _executor.submit(_run_grading, assignment_id, [answer_id])
    except Exception:
        _queue_slots.release()
        with SessionLocal() as db:
            answer = db.get(Answer, answer_id)
            if answer is not None and answer.status == "queued":
                answer.status = "failed"
                answer.error = "Unable to queue grading; please retry."
                db.commit()
        raise HTTPException(status_code=503, detail="Unable to queue grading; please retry.")
    return {
        "answer_id": answer_id,
        "assignment_id": assignment_id,
        "status": "queued",
        "queued": 1,
        "demo_mode": DEMO_MODE,
    }


@router.get("/assignments/{assignment_id}/progress")
def assignment_progress(assignment_id: str) -> dict[str, Any]:
    with SessionLocal() as db:
        assignment = _assignment_or_404(db, assignment_id)
        answers = db.scalars(select(Answer).where(Answer.assignment_id == assignment_id)).all()
        counts = {key: sum(a.status == key for a in answers) for key in ("pending", "queued", "grading", "completed", "failed")}
        percent = round(sum(a.progress for a in answers) / len(answers)) if answers else 0
        if counts["queued"] or counts["grading"]:
            status = "grading"
        elif counts["pending"]:
            status = "pending"
        elif counts["failed"] and not counts["completed"]:
            status = "failed"
        else:
            status = "completed"
        return {
            "assignment_id": assignment.id, "status": status, "progress": percent,
            "total": len(answers), "completed": counts["completed"], "failed": counts["failed"],
            "queued": counts["queued"], "grading": counts["grading"], "demo_mode": DEMO_MODE,
        }


@router.get("/assignments/{assignment_id}/answers")
def list_answers(assignment_id: str, status: str | None = None) -> dict[str, Any]:
    with SessionLocal() as db:
        _assignment_or_404(db, assignment_id)
        query = select(Answer).where(Answer.assignment_id == assignment_id).order_by(Answer.updated_at.desc())
        if status:
            query = query.where(Answer.review_status == status)
        answers = db.scalars(query).all()
        assignment = db.get(Assignment, assignment_id)
        maxima = {q["id"]: q["maximum_points"] for q in assignment.questions}
        return {
            "items": [_answer_json(answer, maxima.get(answer.question_id)) for answer in answers],
            "demo_mode": DEMO_MODE,
        }


@router.get("/answers/{answer_id}")
def get_answer(answer_id: str) -> dict[str, Any]:
    with SessionLocal() as db:
        answer = _answer_or_404(db, answer_id)
        assignment = db.get(Assignment, answer.assignment_id)
        question = next((q for q in assignment.questions if q["id"] == answer.question_id), {})
        return _answer_json(answer, question.get("maximum_points"))


@router.get("/answers/{answer_id}/crop")
def get_answer_crop(answer_id: str) -> Response:
    with SessionLocal() as db:
        answer = _answer_or_404(db, answer_id)
        try:
            content = read_blob(answer.crop_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Answer crop not found.") from exc
    return Response(content, media_type="image/png")


@router.get("/answers/{answer_id}/source-page")
def get_answer_source_page(answer_id: str) -> Response:
    with SessionLocal() as db:
        answer = _answer_or_404(db, answer_id)
        if not answer.has_source_pdf:
            raise HTTPException(status_code=404, detail="Original source page is unavailable.")
        submission = db.get(Submission, answer.submission_id)
        assignment = db.get(Assignment, answer.assignment_id)
        if submission is None or assignment is None or not submission.source_path:
            raise HTTPException(status_code=404, detail="Original source page is unavailable.")
        source_path = submission.source_path
        page_index = answer.page_index
        rotation = assignment.template_rotation
    try:
        png = render_page(read_blob(source_path), page_index, rotation)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Original source page is unavailable.") from exc
    return Response(png, media_type="image/png")


@router.patch("/answers/{answer_id}/review")
def review_answer(answer_id: str, payload: ReviewRequest) -> dict[str, Any]:
    with SessionLocal() as db:
        answer = _answer_or_404(db, answer_id)
        assignment = _assignment_or_404(db, answer.assignment_id)
        question = next((q for q in assignment.questions if q["id"] == answer.question_id), None)
        if not question:
            raise HTTPException(status_code=422, detail="Answer question no longer exists.")
        maximum = float(question["maximum_points"])
        changes = payload.model_dump(exclude_unset=True)
        supplied_criteria = changes.get("criteria_results")
        if supplied_criteria is not None:
            maxima, _ = _rubric(question)
            seen: set[str] = set()
            normalized = []
            for item in supplied_criteria:
                criterion_id = str(item.get("criterion_id") or item.get("id") or "")
                points = item.get("points_awarded", item.get("points", 0))
                if criterion_id not in maxima or criterion_id in seen:
                    raise HTTPException(status_code=422, detail="Review contains an unknown or duplicate criterion ID.")
                if not isinstance(points, (int, float)) or points < 0 or points > maxima[criterion_id]:
                    raise HTTPException(status_code=422, detail=f"Points for {criterion_id} are outside the allowed range.")
                seen.add(criterion_id)
                state = item.get("status") or ("awarded" if points > 0 else "not_awarded")
                if state not in {"awarded", "not_awarded", "uncertain"}:
                    raise HTTPException(status_code=422, detail="Invalid criterion status.")
                evidence = item.get("evidence_from_solution", item.get("evidence", []))
                if isinstance(evidence, str):
                    evidence = evidence[:2000]
                elif isinstance(evidence, list) and all(isinstance(entry, str) for entry in evidence):
                    evidence = [entry[:1000] for entry in evidence[:10]]
                else:
                    raise HTTPException(status_code=422, detail="Criterion evidence must be text.")
                normalized.append(
                    {"criterion_id": criterion_id, "status": state, "passed": points > 0,
                     "points_awarded": float(points), "comment": str(item.get("comment", ""))[:2000],
                     "evidence_from_solution": evidence}
                )
            if seen != set(maxima):
                raise HTTPException(status_code=422, detail="Review must include every rubric criterion.")
            total = round(sum(item["points_awarded"] for item in normalized), 4)
            if total > maximum + 1e-6:
                raise HTTPException(status_code=422, detail="Review score exceeds the question maximum.")
            answer.human_criteria_results = normalized
            answer.human_score = total
            answer.teacher_overridden = True
        explicit_score = changes.get("score", changes.get("points"))
        if explicit_score is not None:
            if explicit_score > maximum:
                raise HTTPException(status_code=422, detail="Review score exceeds the question maximum.")
            answer.human_score = round(explicit_score, 4)
            answer.teacher_overridden = True
        if "transcription" in changes:
            answer.transcription = changes["transcription"]
            answer.teacher_overridden = True
        if "teacher_comment" in changes or "feedback" in changes:
            answer.teacher_comment = changes.get("teacher_comment", changes.get("feedback")) or ""
        if "approved" in changes:
            if changes["approved"] is True:
                raise HTTPException(status_code=409, detail="Use the approve endpoint to approve a grade.")
            answer.approved = changes["approved"]
            answer.review_status = "approved" if answer.approved else "reopened"
        elif "review_status" in changes:
            if changes["review_status"] == "approved":
                raise HTTPException(status_code=409, detail="Use the approve endpoint to approve a grade.")
            answer.review_status = changes["review_status"]
            answer.approved = changes["review_status"] == "approved"
        elif changes:
            answer.review_status = "reviewed"
        db.commit()
        db.refresh(answer)
        return _answer_json(answer, maximum)


@router.post("/answers/{answer_id}/approve")
def approve_answer(answer_id: str) -> dict[str, Any]:
    with SessionLocal() as db:
        answer = _answer_or_404(db, answer_id)
        if answer.suggested_score is None and answer.human_score is None:
            raise HTTPException(status_code=409, detail="Grade the answer before approving it.")
        assignment = db.get(Assignment, answer.assignment_id)
        question = next((q for q in assignment.questions if q["id"] == answer.question_id), {})
        answer.approved = True
        answer.review_status = "approved"
        db.commit()
        db.refresh(answer)
        return _answer_json(answer, question.get("maximum_points"))


@router.post("/answers/{answer_id}/retry-crop")
def retry_crop(
    answer_id: str,
    page_index: int = Form(ge=0),
    region_json: str = Form(),
) -> dict[str, Any]:
    try:
        region_data = json.loads(region_json)
        region = _region(region_data)
        box = NormalizedBox.model_validate(region)
    except (ValueError, ValidationError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid crop region.") from exc
    with SessionLocal() as db:
        answer = _answer_or_404(db, answer_id)
        submission = db.get(Submission, answer.submission_id)
        assignment = db.get(Assignment, answer.assignment_id)
        if submission is None or not submission.source_path:
            raise HTTPException(status_code=409, detail="Original PDF is unavailable.")
        if page_index >= submission.page_count:
            raise HTTPException(status_code=422, detail="Page index is outside the source PDF.")
        try:
            png = crop_page(
                read_blob(submission.source_path),
                page_index,
                box,
                assignment.template_rotation if assignment else 0,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        answer.crop_path = save_blob(answer.assignment_id, "crops", png, ".png")
        answer.page_index = page_index
        if not answer.teacher_overridden and not answer.approved:
            answer.status, answer.progress, answer.error = "pending", 0, None
        db.commit()
        db.refresh(answer)
        assignment = db.get(Assignment, answer.assignment_id)
        question = next((q for q in assignment.questions if q["id"] == answer.question_id), {})
        return _answer_json(answer, question.get("maximum_points"))


@router.post("/answers/{answer_id}/reopen")
def reopen_answer(answer_id: str) -> dict[str, Any]:
    with SessionLocal() as db:
        answer = _answer_or_404(db, answer_id)
        if not answer.approved:
            raise HTTPException(status_code=409, detail="Only approved answers can be reopened.")
        assignment = db.get(Assignment, answer.assignment_id)
        question = next((q for q in assignment.questions if q["id"] == answer.question_id), {})
        answer.approved = False
        answer.review_status = "reopened"
        db.commit()
        db.refresh(answer)
        return _answer_json(answer, question.get("maximum_points"))


@router.get("/assignments/{assignment_id}/export")
def export_assignment(assignment_id: str) -> Response:
    with SessionLocal() as db:
        assignment = _assignment_or_404(db, assignment_id)
        answers = db.scalars(
            select(Answer).where(Answer.assignment_id == assignment_id, Answer.approved.is_(True))
        ).all()
        questions = {q["id"]: q for q in assignment.questions}
        submissions = {s.id: s for s in db.scalars(select(Submission).where(Submission.assignment_id == assignment_id)).all()}
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["anonymous_student_id", "question_id", "question", "points", "maximum_points", "review_status"])
    for answer in answers:
        question = questions.get(answer.question_id, {})
        points = _answer_score(answer)
        writer.writerow(
            [answer.anonymous_student_id or "Student 00", answer.question_id, question.get("title", ""),
             "" if points is None else points, question.get("maximum_points", ""), answer.review_status]
        )
    return Response(
        output.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="assignment-{assignment_id}.csv"'},
    )


@router.get("/assignments/{assignment_id}/answers/{answer_id}")
def assignment_answer_alias(assignment_id: str, answer_id: str) -> dict[str, Any]:
    with SessionLocal() as db:
        answer = _answer_or_404(db, answer_id)
        if answer.assignment_id != assignment_id:
            raise HTTPException(status_code=404, detail="Answer not found.")
        return _answer_json(answer)
