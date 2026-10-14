import io
from pathlib import Path

import pymupdf
import pytest
from docx import Document
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from main import app
from persistence import (
    AcademicAssignment,
    AcademicGrade,
    AcademicSubmission,
    Answer,
    Assignment,
    AssignmentFamily,
    CourseEnrollment,
    CourseOffering,
    OriginalityReport,
    SessionLocal,
    Submission,
    storage_path,
)


def _pdf(text: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((48, 60), text)
    content = document.tobytes()
    document.close()
    return content


def _docx(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _cleanup_test_data(
    academic_ids: list[str],
    legacy_ids: list[str],
    family_ids: list[str],
    submission_ids: list[str],
    legacy_submission_ids: list[str],
    stored_files: list[str],
    legacy_files: list[str],
    offering_ids: list[str],
) -> None:
    with SessionLocal() as db:
        for submission_id in submission_ids:
            db.execute(
                delete(OriginalityReport).where(
                    (OriginalityReport.submission_id == submission_id)
                    | (OriginalityReport.candidate_submission_id == submission_id)
                )
            )
            db.execute(delete(AcademicGrade).where(AcademicGrade.submission_id == submission_id))
            db.execute(delete(AcademicSubmission).where(AcademicSubmission.id == submission_id))
        for legacy_submission_id in legacy_submission_ids:
            if legacy_submission_id:
                db.execute(delete(Answer).where(Answer.submission_id == legacy_submission_id))
                db.execute(delete(Submission).where(Submission.id == legacy_submission_id))
        for assignment_id in academic_ids:
            db.execute(
                delete(OriginalityReport).where(
                    OriginalityReport.submission_id.in_(
                        select(AcademicSubmission.id).where(
                            AcademicSubmission.assignment_id == assignment_id
                        )
                    )
                )
            )
            db.execute(delete(AcademicGrade).where(AcademicGrade.assignment_id == assignment_id))
            db.execute(delete(AcademicSubmission).where(AcademicSubmission.assignment_id == assignment_id))
            db.execute(delete(AcademicAssignment).where(AcademicAssignment.id == assignment_id))
        for legacy_id in set(legacy_ids):
            if legacy_id:
                db.execute(delete(Answer).where(Answer.assignment_id == legacy_id))
                db.execute(delete(Submission).where(Submission.assignment_id == legacy_id))
                db.execute(delete(Assignment).where(Assignment.id == legacy_id))
        for family_id in set(family_ids):
            db.execute(delete(AssignmentFamily).where(AssignmentFamily.id == family_id))
        for offering_id in offering_ids:
            db.execute(delete(CourseEnrollment).where(CourseEnrollment.offering_id == offering_id))
            db.execute(delete(CourseOffering).where(CourseOffering.id == offering_id))
        db.commit()
    for file_path in set(stored_files + legacy_files):
        storage_path(*Path(file_path).parts).unlink(missing_ok=True)


def test_academic_end_to_end_seed_reuse_submissions_originality_and_publish(request: pytest.FixtureRequest):
    academic_ids: list[str] = []
    legacy_ids: list[str] = []
    family_ids: list[str] = []
    submission_ids: list[str] = []
    legacy_submission_ids: list[str] = []
    stored_files: list[str] = []
    legacy_files: list[str] = []
    offering_ids: list[str] = []
    request.addfinalizer(
        lambda: _cleanup_test_data(
            academic_ids,
            legacy_ids,
            family_ids,
            submission_ids,
            legacy_submission_ids,
            stored_files,
            legacy_files,
            offering_ids,
        )
    )
    with TestClient(app) as client:
        teacher_courses = client.get("/academic/courses?role=teacher")
        assert teacher_courses.status_code == 200
        course = next(item for item in teacher_courses.json()["items"] if item["code"] == "PHY101")
        assert course["instructor"] == "Dr. Ada Rivera"
        assert {row["academic_year"] for row in course["offerings"]} >= {"2024", "2025", "2026"}
        with SessionLocal() as db:
            historical_pdf = db.get(AcademicSubmission, "phy101-history-submission-2024")
            historical_docx = db.get(AcademicSubmission, "phy101-history-submission-2025")
            assert historical_pdf.file_type == "pdf"
            assert storage_path(*Path(historical_pdf.file_path).parts).is_file()
            assert historical_docx.file_type == "docx"
            assert storage_path(*Path(historical_docx.file_path).parts).is_file()
        student_courses = client.get("/academic/courses?role=student")
        assert student_courses.status_code == 200
        assert len(next(item for item in student_courses.json()["items"] if item["id"] == course["id"])["offerings"]) == 3

        fall_2026 = next(row for row in course["offerings"] if row["academic_year"] == "2026")
        offering = client.get(f"/academic/offerings/{fall_2026['id']}")
        assert offering.status_code == 200
        assert offering.json()["course"]["code"] == "PHY101"
        source = next(row for row in offering.json()["assignments"] if row["id"] == "phy101-force-assignment-2026")
        original_assignment = client.get("/academic/offerings/phy101-fall-2024/assignments")
        source_2024 = original_assignment.json()["items"][0]

        reused = client.post(
            f"/academic/assignments/{source_2024['id']}/reuse",
            json={
                "offering_id": fall_2026["id"],
                "available_at": "2026-08-01T00:00:00Z",
                "due_at": "2026-12-01T00:00:00Z",
                "copy_rubric": True,
                "copy_reference_solution": False,
                "copy_template": False,
            },
        )
        assert reused.status_code == 201, reused.text
        reused_data = reused.json()
        academic_ids.append(reused_data["id"])
        with SessionLocal() as db:
            legacy_ids.append(db.get(AcademicAssignment, reused_data["id"]).legacy_assignment_id)
        assert reused_data["family_id"] == source_2024["family_id"]
        assert reused_data["submission_count"] == 0
        assert reused_data["copied"] == {
            "rubric": True,
            "reference_solution": False,
            "template": False,
            "submissions": False,
            "grades": False,
        }
        assert all(not question["reference_solution"] for question in reused_data["questions"])

        strong_text = (
            "For a block on a frictionless incline, choose axes parallel and perpendicular to the surface. "
            "The gravitational force points vertically downward, so resolve it into components along these axes. "
            "The parallel component is mg sin(theta), directed down the slope. "
            "The perpendicular component is mg cos(theta), directed into the surface."
        )
        uploaded = client.post(
            f"/academic/assignments/{source['id']}/submissions",
            files={"file": ("physics-work.pdf", _pdf(strong_text), "application/pdf")},
        )
        assert uploaded.status_code == 201, uploaded.text
        uploaded_data = uploaded.json()
        submission_ids.append(uploaded_data["id"])
        with SessionLocal() as db:
            stored_files.append(db.get(AcademicSubmission, uploaded_data["id"]).file_path)
        assert uploaded_data["file_type"] == "pdf"
        assert uploaded_data["extracted_text"].strip()
        reports = uploaded_data["originality_reports"]
        assert len(reports) == 1
        report = reports[0]
        assert report["candidate_submission_id"] == "phy101-history-submission-2024"
        assert report["match_scope"] == "assignment_family"
        assert report["eligible_token_count"] > 0
        assert report["minimum_passage_tokens"] == 8
        assert report["offset_unit"] == "Unicode code points, half-open [start, end)"
        assert report["match_ratio"] == round(
            report["matched_token_count"] / report["eligible_token_count"], 6
        )
        evidence = report["evidence"][0]
        assert (
            uploaded_data["extracted_text"][
                evidence["source_offsets"]["start"]:evidence["source_offsets"]["end"]
            ]
            == evidence["source_excerpt"]
        )
        with SessionLocal() as db:
            historical_text = db.get(AcademicSubmission, report["candidate_submission_id"]).extracted_text
        assert (
            historical_text[
                evidence["candidate_offsets"]["start"]:evidence["candidate_offsets"]["end"]
            ]
            == evidence["candidate_excerpt"]
        )
        report_id = report["id"]
        assert client.get(f"/academic/submissions/{uploaded_data['id']}/originality").json()["items"][0]["id"] == report_id
        review = client.patch(
            f"/academic/reports/{report_id}/review",
            json={"review_status": "reviewed", "teacher_notes": "Compare the cited working in context."},
        )
        assert review.status_code == 200
        assert review.json()["review_status"] == "reviewed"
        assert "not a misconduct finding" in review.json()["interpretation"]
        assert any(row["id"] == report_id for row in client.get("/academic/teacher/originality").json()["items"])
        archive = client.get(f"/academic/teacher/assignments/{source['id']}/archive")
        assert archive.status_code == 200
        assert {item["file_type"] for item in archive.json()["items"]} >= {"pdf", "docx"}

        with SessionLocal() as db:
            academic_submission = db.get(AcademicSubmission, uploaded_data["id"])
            legacy_submission_ids.append(academic_submission.legacy_submission_id)
            legacy_file_path = db.get(Submission, academic_submission.legacy_submission_id).source_path
            if legacy_file_path:
                legacy_files.append(legacy_file_path)
            legacy_assignment_id = db.get(AcademicAssignment, source["id"]).legacy_assignment_id
            db.add(
                Answer(
                    assignment_id=legacy_assignment_id,
                    submission_id=academic_submission.legacy_submission_id,
                    question_id="q-force",
                    anonymous_student_id="Student 01",
                    crop_path="",
                    page_index=0,
                    suggested_score=8,
                    human_score=8,
                    approved=True,
                    review_status="approved",
                )
            )
            db.commit()
        published = client.post(f"/academic/assignments/{source['id']}/publish")
        assert published.status_code == 200
        assert published.json()["published_count"] == 1
        grades = client.get("/academic/student/grades")
        assert grades.status_code == 200
        assert any(
            row["submission_id"] == uploaded_data["id"] and row["points"] == 8
            for row in grades.json()["items"]
        )

        formula_assignment = client.post(
            "/academic/assignments",
            json={
                "offering_id": fall_2026["id"],
                "title": "Formula-only comparison",
                "assignment_type": "homework",
                "maximum_score": 5,
                "originality_scope": "course",
                "questions": [],
            },
        )
        assert formula_assignment.status_code == 201, formula_assignment.text
        formula_data = formula_assignment.json()
        academic_ids.append(formula_data["id"])
        with SessionLocal() as db:
            legacy_ids.append(db.get(AcademicAssignment, formula_data["id"]).legacy_assignment_id)
            family_ids.append(db.get(AcademicAssignment, formula_data["id"]).family_id)
        docx_upload = client.post(
            f"/academic/assignments/{formula_data['id']}/submissions",
            files={
                "file": (
                    "formula.docx",
                    _docx("In this introductory example the familiar formula F=ma is used."),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        assert docx_upload.status_code == 201, docx_upload.text
        docx_data = docx_upload.json()
        submission_ids.append(docx_data["id"])
        with SessionLocal() as db:
            stored_files.append(db.get(AcademicSubmission, docx_data["id"]).file_path)
        assert docx_data["file_type"] == "docx"
        assert "F=ma" in docx_data["extracted_text"]
        assert docx_data["originality_reports"] == []

        deadline = client.post(
            "/academic/assignments",
            json={
                "offering_id": fall_2026["id"],
                "title": "Expired deadline test",
                "maximum_score": 2,
                "due_at": "2020-01-01T00:00:00Z",
            },
        )
        assert deadline.status_code == 201, deadline.text
        deadline_data = deadline.json()
        academic_ids.append(deadline_data["id"])
        with SessionLocal() as db:
            legacy_ids.append(db.get(AcademicAssignment, deadline_data["id"]).legacy_assignment_id)
            family_ids.append(db.get(AcademicAssignment, deadline_data["id"]).family_id)
        late = client.post(
            f"/academic/assignments/{deadline_data['id']}/submissions",
            files={"file": ("late.pdf", _pdf("late work"), "application/pdf")},
        )
        assert late.status_code == 409
        assert "deadline" in late.json()["detail"]

        offering_created = client.post(
            "/academic/offerings",
            json={
                "course_id": course["id"],
                "academic_year": "2098",
                "term": "Fall",
                "section": "99",
            },
        )
        assert offering_created.status_code == 201, offering_created.text
        offering_ids.append(offering_created.json()["id"])
        enrolled = client.post("/academic/enroll", json={"class_code": offering_created.json()["class_code"]})
        assert enrolled.status_code == 201
        assert enrolled.json()["student_id"] == "demo-student-001"
