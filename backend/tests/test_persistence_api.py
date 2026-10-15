import io
import shutil
import uuid

import pymupdf
import pytest
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import delete

import assignment_api
import services.ai_grader as ai_grader
from google.genai.errors import APIError
from assignment_api import (
    DEMO_ASSIGNMENT_ID,
    _demo_seed,
    _answer_json,
    export_assignment,
    resolve_demo_mode,
    validate_grading,
)
from fastapi.testclient import TestClient
from main import app
from persistence import Answer, Assignment, SessionLocal, Submission, init_db, read_blob, save_blob, storage_path
from schemas import CriterionEval, GradingResult
from services.pdf_slicer import NormalizedBox, crop_page

init_db()


def test_demo_mode_fallback_preserves_configured_gemini():
    assert resolve_demo_mode(None, None) is True
    assert resolve_demo_mode(None, "configured-key") is False
    assert resolve_demo_mode("true", "configured-key") is True
    assert resolve_demo_mode("false", None) is False


def test_grader_retries_only_transient_api_failures(monkeypatch):
    attempts = 0
    delays: list[float] = []
    result = GradingResult(
        transcribed_latex="x",
        criteria_results=[],
        total_score=0,
        overall_feedback="ok",
    )

    def transient_then_success(*args):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise APIError(429, {"error": {"status": "RESOURCE_EXHAUSTED"}})
        if attempts == 2:
            raise APIError(503, {"error": {"status": "UNAVAILABLE"}})
        return result

    monkeypatch.setattr(ai_grader, "grade_image", transient_then_success)
    monkeypatch.setattr(ai_grader.time, "sleep", delays.append)
    assert ai_grader.grade_image_with_retry(b"image", "prompt", "solution", "rubric") is result
    assert attempts == 3
    assert delays == [0.25, 0.5]

    attempts = 0

    def invalid_response(*args):
        nonlocal attempts
        attempts += 1
        raise GradingResult.model_validate({})

    monkeypatch.setattr(ai_grader, "grade_image", invalid_response)
    with pytest.raises(ValidationError):
        ai_grader.grade_image_with_retry(b"image", "prompt", "solution", "rubric")
    assert attempts == 1


def test_generated_storage_paths_and_roundtrip():
    assignment_id = str(uuid.uuid4())
    saved = save_blob(assignment_id, "crops", b"image", ".png")
    assert read_blob(saved) == b"image"
    assert storage_path(*saved.split("/")).is_relative_to(storage_path())
    with pytest.raises(ValueError):
        storage_path("..", "outside")
    storage_path(*saved.split("/")).unlink()


def test_pdf_crop_supports_multipage_and_bounds():
    pdf = pymupdf.open()
    pdf.new_page(width=400, height=200)
    pdf.new_page(width=300, height=400)
    contents = pdf.tobytes()
    pdf.close()
    box = NormalizedBox(id="q1", title="Answer", x1=0.1, y1=0.1, x2=0.9, y2=0.9)
    png = crop_page(contents, 1, box)
    with Image.open(io.BytesIO(png)) as image:
        assert image.format == "PNG"
        assert image.width > 0 and image.height > 0
    with pytest.raises(ValueError):
        crop_page(contents, 2, box)
    full_page = NormalizedBox(id="all", title="Page", x1=0, y1=0, x2=1, y2=1)
    rotated = crop_page(contents, 0, full_page, rotation=90)
    with Image.open(io.BytesIO(rotated)) as image:
        assert image.height > image.width
    with pytest.raises(ValueError, match="Rotation"):
        crop_page(contents, 0, full_page, rotation=45)


def test_rubric_ids_and_totals_are_validated_and_deterministic():
    question = {
        "id": "q1",
        "maximum_points": 5,
        "criteria": [
            {"id": "work", "criterion_id": "work", "description": "Work", "maximum_points": 2},
            {"id": "answer", "criterion_id": "answer", "description": "Answer", "maximum_points": 3},
        ],
    }
    result = GradingResult(
        transcribed_latex="x=2",
        criteria_results=[
            CriterionEval(
                criterion_id="work", passed=True, points_awarded=1.5, comment="Good",
                evidence=["Line 1: correct setup"],
            ),
            CriterionEval(criterion_id="answer", passed=True, points_awarded=3, comment="Correct"),
        ],
        total_score=999,
        overall_feedback="Good",
        uncertainty=0.4,
        requires_human_attention=True,
        attention_reasons=["Check one handwritten symbol."],
        transcription_notes=["One symbol was unclear."],
    )
    validated = validate_grading(result, question)
    assert validated["total_score"] == 4.5
    assert validated["uncertainty"] == 0.4
    assert validated["requires_human_attention"] is True
    assert validated["attention_reasons"] == ["Check one handwritten symbol."]
    assert validated["transcription_notes"] == ["One symbol was unclear."]
    assert validated["criteria_results"][0]["evidence"] == ["Line 1: correct setup"]
    result.criteria_results[0].criterion_id = "not-in-rubric"
    with pytest.raises(ValueError, match="unknown"):
        validate_grading(result, question)

    result.criteria_results[0].criterion_id = "work"
    result.criteria_results[0].points_awarded = 2.1
    with pytest.raises(ValueError, match="maximum"):
        validate_grading(result, question)


def test_csv_export_contains_approved_answers_only():
    assignment_id = str(uuid.uuid4())
    with SessionLocal() as db:
        assignment = Assignment(
            id=assignment_id,
            title="Test",
            subject="Math",
            status="active",
            questions=[{"id": "q1", "title": "Question", "maximum_points": 4, "criteria": []}],
        )
        db.add(assignment)
        db.flush()
        submission = Submission(
            assignment_id=assignment.id,
            student_name="Student 01",
            anonymous_student_id="Student 01",
            source_path="", page_count=1
        )
        db.add(submission)
        db.flush()
        db.add_all(
            [
                Answer(
                    assignment_id=assignment.id,
                    submission_id=submission.id,
                    question_id="q1",
                    anonymous_student_id="Student 01",
                    crop_path="",
                    page_index=0,
                    suggested_score=3,
                    approved=True,
                    review_status="approved",
                ),
                Answer(
                    assignment_id=assignment.id,
                    submission_id=submission.id,
                    question_id="q1",
                    anonymous_student_id="Student 01",
                    crop_path="",
                    page_index=0,
                    suggested_score=2,
                    approved=False,
                ),
            ]
        )
        db.commit()
    try:
        response = export_assignment(assignment_id)
        text = response.body.decode("utf-8-sig")
        assert "anonymous_student_id,question_id,question,points,maximum_points,review_status" in text
        assert text.count("Student 01") == 1
        assert "Hidden name" not in text
    finally:
        with SessionLocal() as db:
            db.execute(delete(Answer).where(Answer.assignment_id == assignment_id))
            db.execute(delete(Submission).where(Submission.assignment_id == assignment_id))
            db.execute(delete(Assignment).where(Assignment.id == assignment_id))
            db.commit()


def test_rest_submission_review_retry_and_reopen_flow():
    pdf = pymupdf.open()
    pdf.new_page(width=400, height=500)
    pdf.new_page(width=400, height=500)
    pdf_bytes = pdf.tobytes()
    pdf.close()
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/api/health").json()["status"] == "ok"
        created = client.post(
            "/assignments",
            json={
                "title": "Route flow",
                "subject": "Math",
                "status": "active",
                "questions": [
                    {
                        "id": "q1",
                        "title": "Question 1",
                        "statement": "Solve x = 2",
                        "reference_solution": "x = 2",
                        "maximum_points": 4,
                        "criteria": [
                            {"id": "answer", "description": "Correct answer", "maximum_points": 4}
                        ],
                    },
                    {
                        "id": "q2",
                        "title": "Question 2",
                        "statement": "Find the force",
                        "reference_solution": "F = ma",
                        "maximum_points": 2,
                        "criteria": [
                            {"id": "force", "description": "Correct force", "maximum_points": 2}
                        ],
                    },
                ],
            },
        )
        assert created.status_code == 201
        assignment_id = created.json()["id"]
        assert created.json()["created_at"]
        assert created.json()["reviewed_count"] == 0
        assert created.json()["questions"][0]["criteria"][0]["criterion_id"] == "answer"
        template = client.post(
            f"/assignments/{assignment_id}/template",
            json={
                "rotation": 90,
                "regions": [
                    {"question_id": "q1", "page_index": 1, "x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.8},
                    {"question_id": "q2", "page_index": 0, "x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.8},
                ],
            },
        )
        assert template.status_code == 200
        assert template.json()["template_rotation"] == 90
        assert template.json()["template"]["rotation"] == 90
        assert template.json()["created_at"]
        assert template.json()["reviewed_count"] == 0
        uploaded = client.post(
            f"/assignments/{assignment_id}/submissions",
            files={"file": ("source.pdf", pdf_bytes, "application/pdf")},
        )
        assert uploaded.status_code == 201
        assert uploaded.json()["submission_count"] == 2
        assert uploaded.json()["answer_count"] == 4
        answer = uploaded.json()["answers"][0]
        assert answer["anonymous_student_id"] == "Student 01"
        assert answer["page_index"] == 0
        assert answer["page_number"] == 1
        assert uploaded.json()["answers"][2]["anonymous_student_id"] == "Student 02"
        assert uploaded.json()["answers"][2]["page_index"] == 1
        assert uploaded.json()["submissions"][0]["anonymous_student_id"] == "Student 01"
        with SessionLocal() as db:
            stored_submission = db.get(Submission, uploaded.json()["submissions"][0]["id"])
            assert stored_submission.student_name == "Student 01"
            assert stored_submission.student_name != "source.pdf"
            for remaining_answer in db.query(Answer).filter(
                Answer.assignment_id == assignment_id,
                Answer.anonymous_student_id == "Student 02",
            ):
                remaining_answer.teacher_overridden = True
                remaining_answer.human_score = 0
            db.commit()
        assert answer["crop_url"].startswith("/answers/")
        assert answer["maximum_points"] == 4
        assert client.get(answer["crop_url"]).status_code == 200
        assert answer["source_page_url"] == f"/answers/{answer['id']}/source-page"
        assert client.get(answer["source_page_url"]).headers["content-type"] == "image/png"

        with SessionLocal() as db:
            stored_answer = db.get(Answer, answer["id"])
            stored_answer.feedback = "AI feedback stays unchanged."
            db.commit()
        reviewed = client.patch(
            f"/answers/{answer['id']}/review",
            json={
                "points": 3.5,
                "teacher_comment": "Teacher note.",
                "criteria_results": [
                    {
                        "criterion_id": "answer",
                        "points_awarded": 3.5,
                        "comment": "Промежуточный шаг проверен.",
                        "evidence_from_solution": "x = 2",
                    },
                ],
            },
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["points"] == 3.5
        assert reviewed.json()["teacher_comment"] == "Teacher note."
        assert reviewed.json()["grading"]["overall_feedback"] == "AI feedback stays unchanged."
        assert reviewed.json()["grading"]["criteria_results"][0]["evidence_from_solution"] == "x = 2"
        # One reviewed answer does not make a two-question submission complete.
        assert client.get(f"/assignments/{assignment_id}").json()["reviewed_count"] == 0
        with SessionLocal() as db:
            second_answer = db.query(Answer).filter(
                Answer.assignment_id == assignment_id,
                Answer.anonymous_student_id == "Student 01",
                Answer.question_id == "q2",
            ).one()
            second_answer.teacher_overridden = True
            second_answer.human_score = 1
            db.commit()
        assert client.post(f"/answers/{answer['id']}/approve").status_code == 200
        assert "3.5" in client.get(f"/assignments/{assignment_id}/export").text

        retried = client.post(
            f"/answers/{answer['id']}/retry-crop",
            data={
                "page_index": "0",
                "region_json": '{"x1":0.2,"y1":0.2,"x2":0.7,"y2":0.7}',
            },
        )
        assert retried.status_code == 200
        assert retried.json()["points"] == 3.5
        assert client.post(f"/assignments/{assignment_id}/grade").json()["queued"] == 0
        reopened = client.post(f"/answers/{answer['id']}/reopen")
        assert reopened.json()["review_status"] == "reopened"
        assert reopened.json()["points"] == 3.5
        assert client.post(f"/assignments/{assignment_id}/grade").json()["queued"] == 0
        assert "3.5" not in client.get(f"/assignments/{assignment_id}/export").text
        assert client.delete(f"/assignments/{assignment_id}").status_code == 204
        assert not storage_path(assignment_id).exists()


def test_demo_seed_has_physics_rubric_and_four_labeled_examples():
    try:
        with SessionLocal() as db:
            _demo_seed(db)
            assignment = db.get(Assignment, DEMO_ASSIGNMENT_ID)
            assert assignment is not None
            assert assignment.subject == "Физика"
            assert len(assignment.questions) == 3
            criteria = [question["criteria"][0] for question in assignment.questions]
            assert sum(item["maximum_points"] for item in criteria) == 5
            assert [
                (item["criterion_id"], item["maximum_points"])
                for item in criteria
            ] == [("C1", 2), ("C2", 2), ("C3", 1)]
            answers = db.query(Answer).filter_by(assignment_id=DEMO_ASSIGNMENT_ID).all()
            assert len(answers) == 12
            cases = {answer.grading_metadata["demo_case"] for answer in answers}
            assert cases == {
                "correct",
                "incorrect_decomposition",
                "arithmetic_error",
                "partially_unreadable",
            }
            assert all(len(answer.criteria_results) == 1 for answer in answers)
            assert all(all(item["evidence"] for item in answer.criteria_results) for answer in answers)
            unclear = next(a for a in answers if a.grading_metadata["demo_case"] == "partially_unreadable")
            assert unclear.grading_metadata["requires_human_attention"] is True
            assert unclear.grading_metadata["attention_reasons"]
            payload = _answer_json(unclear, maximum_points=5)
            assert payload["grading"]["requires_human_attention"] is True
            assert payload["grading"]["transcription_notes"]
            assert payload["grading"]["criteria_results"][0]["evidence"]
            assert len(assignment.template_regions) == 3
    finally:
        with SessionLocal() as db:
            db.execute(delete(Answer).where(Answer.assignment_id == DEMO_ASSIGNMENT_ID))
            db.execute(delete(Submission).where(Submission.assignment_id == DEMO_ASSIGNMENT_ID))
            db.execute(delete(Assignment).where(Assignment.id == DEMO_ASSIGNMENT_ID))
            db.commit()
        shutil.rmtree(storage_path(DEMO_ASSIGNMENT_ID), ignore_errors=True)


def test_retry_endpoint_queues_only_pending_or_failed_answer(monkeypatch):
    assignment_id = str(uuid.uuid4())
    answer_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(
            Assignment(
                id=assignment_id,
                title="Retry",
                subject="Physics",
                status="active",
                questions=[{"id": "q1", "title": "Question", "maximum_points": 1, "criteria": []}],
            )
        )
        db.flush()
        submission = Submission(
            assignment_id=assignment_id, student_name="Student", source_path="", page_count=1
        )
        db.add(submission)
        db.flush()
        db.add(
            Answer(
                id=answer_id,
                assignment_id=assignment_id,
                submission_id=submission.id,
                question_id="q1",
                page_index=0,
                status="failed",
                crop_path="generated-crop.png",
            )
        )
        db.commit()

    queued: list[tuple[str, list[str]]] = []

    def capture_job(function, *args):
        queued.append(args)
        assignment_api._queue_slots.release()

    monkeypatch.setattr(assignment_api._executor, "submit", capture_job)
    try:
        with TestClient(app) as client:
            response = client.post(f"/answers/{answer_id}/retry")
            assert response.status_code == 202
            assert response.json()["queued"] == 1
            assert queued == [(assignment_id, [answer_id])]
            assert client.post(f"/answers/{answer_id}/retry").status_code == 409
            with SessionLocal() as db:
                answer = db.get(Answer, answer_id)
                answer.status = "failed"
                answer.teacher_overridden = True
                db.commit()
            assert client.post(f"/answers/{answer_id}/retry").status_code == 409
            with SessionLocal() as db:
                answer = db.get(Answer, answer_id)
                answer.teacher_overridden = False
                answer.approved = True
                db.commit()
            assert client.post(f"/answers/{answer_id}/retry").status_code == 409
    finally:
        with SessionLocal() as db:
            db.execute(delete(Answer).where(Answer.id == answer_id))
            db.execute(delete(Submission).where(Submission.assignment_id == assignment_id))
            db.execute(delete(Assignment).where(Assignment.id == assignment_id))
            db.commit()


def test_crop_failure_is_returned_as_retryable_failed_answer(monkeypatch):
    pdf = pymupdf.open()
    pdf.new_page(width=400, height=500)
    pdf.new_page(width=400, height=500)
    pdf_bytes = pdf.tobytes()
    pdf.close()
    real_crop_page = assignment_api.crop_page

    def fail_second_page(pdf_bytes, page_index, box, rotation=0):
        if page_index == 1:
            raise ValueError("simulated crop failure")
        return real_crop_page(pdf_bytes, page_index, box, rotation)

    monkeypatch.setattr(assignment_api, "crop_page", fail_second_page)
    with TestClient(app) as client:
        too_few = client.post("/assignments", json={"title": "Too few", "questions": [
            {"id": "only", "title": "Only", "maximum_points": 1}
        ]})
        assert too_few.status_code == 422
        created = client.post(
            "/assignments",
            json={
                "title": "Crop failures",
                "questions": [
                    {"id": "q1", "title": "One", "maximum_points": 1},
                    {"id": "q2", "title": "Two", "maximum_points": 1},
                ],
            },
        )
        assert created.status_code == 201
        assignment_id = created.json()["id"]
        one_region = client.post(
            f"/assignments/{assignment_id}/template",
            json={"regions": [{"question_id": "q1", "x1": 0, "y1": 0, "x2": 1, "y2": 1}]},
        )
        assert one_region.status_code == 422
        template = client.post(
            f"/assignments/{assignment_id}/template",
            json={
                "regions": [
                    {"question_id": "q1", "page_index": 0, "x1": 0, "y1": 0, "x2": 1, "y2": 1},
                    {"question_id": "q2", "page_index": 0, "x1": 0, "y1": 0, "x2": 1, "y2": 1},
                ]
            },
        )
        assert template.status_code == 200
        response = client.post(
            f"/assignments/{assignment_id}/submissions",
            files={"file": ("two-pages.pdf", pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 201
        assert response.json()["submission_count"] == 2
        assert response.json()["answer_count"] == 4
        failed = [answer for answer in response.json()["answers"] if answer["anonymous_student_id"] == "Student 02"]
        assert len(failed) == 2
        assert all(answer["status"] == "failed" for answer in failed)
        assert all(answer["crop_url"] is None for answer in failed)
        assert all("retry-crop" in answer["error"] for answer in failed)
        assert client.get(f"/assignments/{assignment_id}/progress").json()["failed"] == 2
        assert client.post(f"/answers/{failed[0]['id']}/retry").status_code == 409
        monkeypatch.setattr(assignment_api, "crop_page", real_crop_page)
        retried_crop = client.post(
            f"/answers/{failed[0]['id']}/retry-crop",
            data={
                "page_index": "1",
                "region_json": '{"id":"q1","title":"One","question_id":"q1","x1":0,"y1":0,"x2":1,"y2":1}',
            },
        )
        assert retried_crop.status_code == 200
        assert retried_crop.json()["status"] == "pending"
        assert retried_crop.json()["page_number"] == 2
        assert client.get(retried_crop.json()["crop_url"]).status_code == 200
        with SessionLocal() as db:
            for other_answer in db.query(Answer).filter(
                Answer.assignment_id == assignment_id,
                Answer.crop_path != "",
            ):
                other_answer.teacher_overridden = True
            db.commit()
        assert client.post(f"/assignments/{assignment_id}/grade").json()["queued"] == 0
        client.delete(f"/assignments/{assignment_id}")


def test_final_grading_error_persists_failed_status(monkeypatch):
    assignment_id = str(uuid.uuid4())
    answer_id = str(uuid.uuid4())
    with SessionLocal() as db:
        assignment = Assignment(
            id=assignment_id,
            title="Failure",
            subject="Physics",
            status="active",
            questions=[
                {
                    "id": "q1",
                    "title": "Question",
                    "maximum_points": 1,
                    "criteria": [{"id": "c1", "criterion_id": "c1", "description": "criterion", "maximum_points": 1}],
                }
            ],
        )
        db.add(assignment)
        db.flush()
        submission = Submission(
            assignment_id=assignment_id, student_name="Student", source_path="", page_count=1
        )
        db.add(submission)
        db.flush()
        db.add(
            Answer(
                id=answer_id,
                assignment_id=assignment_id,
                submission_id=submission.id,
                question_id="q1",
                crop_path="",
                page_index=0,
                status="queued",
            )
        )
        db.commit()

    def fail_grading(*args):
        raise APIError(503, {"error": {"status": "UNAVAILABLE"}})

    monkeypatch.setattr(assignment_api, "DEMO_MODE", False)
    monkeypatch.setattr(assignment_api, "grade_image_with_retry", fail_grading)
    assert assignment_api._queue_slots.acquire(blocking=False)
    assignment_api._run_grading(assignment_id, [answer_id])
    try:
        with SessionLocal() as db:
            answer = db.get(Answer, answer_id)
            assert answer.status == "failed"
            assert answer.progress == 100
            assert answer.error == "Grading failed. Retry or check the server configuration."
    finally:
        with SessionLocal() as db:
            db.execute(delete(Answer).where(Answer.id == answer_id))
            db.execute(delete(Submission).where(Submission.assignment_id == assignment_id))
            db.execute(delete(Assignment).where(Assignment.id == assignment_id))
            db.commit()
