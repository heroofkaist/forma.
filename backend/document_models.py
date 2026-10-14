from datetime import datetime
from uuid import uuid4
from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from persistence import Base, now_utc

class SubmissionDocument(Base):
    __tablename__ = "submission_documents"
    submission_id: Mapped[str] = mapped_column(ForeignKey("academic_submissions.id"), primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    structure: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class CourseMaterial(Base):
    __tablename__ = "course_materials"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    offering_id: Mapped[str] = mapped_column(ForeignKey("academic_offerings.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    visibility: Mapped[str] = mapped_column(String(24), default="teacher_only")
    tags: Mapped[str] = mapped_column(String(500), default="")
    file_path: Mapped[str] = mapped_column(String(500))
    file_name: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(16))
    content_hash: Mapped[str] = mapped_column(String(64))
    structure: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="ready")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class DocumentReview(Base):
    __tablename__ = "document_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    submission_id: Mapped[str] = mapped_column(ForeignKey("academic_submissions.id"), index=True)
    reviewer: Mapped[str] = mapped_column(String(254))
    criteria: Mapped[list] = mapped_column(JSON)
    rubric_snapshot: Mapped[list] = mapped_column(JSON)
    feedback: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class PublishedDocumentReview(Base):
    __tablename__ = "published_document_reviews"
    grade_id: Mapped[str] = mapped_column(ForeignKey("academic_grades.id"), primary_key=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("document_reviews.id"))
