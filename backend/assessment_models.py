"""Append-only rubric, suggestion and teacher-decision versions; never grades."""
from uuid import uuid4
from datetime import datetime
from sqlalchemy import String, ForeignKey, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from persistence import Base, now_utc


class AssessmentRubric(Base):
    __tablename__ = 'assessment_rubrics'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assignment_id: Mapped[str] = mapped_column(ForeignKey('academic_assignments.id'), index=True)
    spec: Mapped[dict] = mapped_column(JSON)
    approved_by: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AssessmentSuggestion(Base):
    __tablename__ = 'assessment_suggestions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    submission_id: Mapped[str] = mapped_column(ForeignKey('academic_submissions.id'), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('document_processing_jobs.id'), unique=True)
    rubric_id: Mapped[str] = mapped_column(ForeignKey('assessment_rubrics.id'))
    interpretation_id: Mapped[str] = mapped_column(ForeignKey('document_interpretations.id'))
    correction_id: Mapped[str | None] = mapped_column(ForeignKey('interpretation_corrections.id'), nullable=True)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AssessmentDecision(Base):
    __tablename__ = 'assessment_decisions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    suggestion_id: Mapped[str] = mapped_column(ForeignKey('assessment_suggestions.id'), index=True)
    reviewer: Mapped[str] = mapped_column(String(254))
    decisions: Mapped[list] = mapped_column(JSON)
    review_id: Mapped[str | None] = mapped_column(ForeignKey('document_reviews.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
