"""Versioned teacher guidance and student revision receipts; no grade mutation."""
from uuid import uuid4
from datetime import datetime
from sqlalchemy import String, ForeignKey, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from persistence import Base, now_utc

class TeachingGuide(Base):
    __tablename__ = 'assessment_teaching_guides'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assignment_id: Mapped[str] = mapped_column(ForeignKey('academic_assignments.id'), index=True)
    content: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class RevisionResponse(Base):
    __tablename__ = 'student_revision_responses'
    submission_id: Mapped[str] = mapped_column(ForeignKey('academic_submissions.id'), primary_key=True)
    source_review_id: Mapped[str] = mapped_column(ForeignKey('document_reviews.id'), index=True)
    content: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
