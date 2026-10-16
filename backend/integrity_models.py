"""Immutable advisory content profiles. Never stores or updates a grade."""
from datetime import datetime
from uuid import uuid4
from sqlalchemy import ForeignKey, String, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from persistence import Base, now_utc

class DocumentIntegrityReport(Base):
    __tablename__ = 'document_integrity_reports'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    submission_id: Mapped[str] = mapped_column(ForeignKey('academic_submissions.id'), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('document_processing_jobs.id'), unique=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
