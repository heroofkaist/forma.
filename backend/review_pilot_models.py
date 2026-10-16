"""Immutable teacher memory, manual page mapping and upload receipts."""
from uuid import uuid4
from datetime import datetime
from sqlalchemy import String, ForeignKey, JSON, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from persistence import Base, now_utc

class ReviewDecisionCard(Base):
    __tablename__ = 'review_decision_cards'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(ForeignKey('academic_courses.id'), index=True)
    source_review_id: Mapped[str] = mapped_column(ForeignKey('document_reviews.id'), index=True)
    signature: Mapped[str] = mapped_column(String(64), index=True)
    dedup_key: Mapped[str] = mapped_column(String(64), unique=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class QuestionPageMap(Base):
    __tablename__ = 'review_question_page_maps'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    submission_id: Mapped[str] = mapped_column(ForeignKey('academic_submissions.id'), index=True)
    question_id: Mapped[str] = mapped_column(String(80))
    signature: Mapped[str] = mapped_column(String(64))
    pages: Mapped[list] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class SubmissionUploadReceipt(Base):
    __tablename__ = 'submission_upload_receipts'
    __table_args__ = (UniqueConstraint('assignment_id', 'student_id', 'request_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assignment_id: Mapped[str] = mapped_column(ForeignKey('academic_assignments.id'), index=True)
    student_id: Mapped[str] = mapped_column(String(80))
    request_id: Mapped[str] = mapped_column(String(36))
    content_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
