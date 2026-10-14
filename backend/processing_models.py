from datetime import datetime
from uuid import uuid4
from sqlalchemy import ForeignKey, String, Integer, DateTime, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from persistence import Base, now_utc

class ProcessingJob(Base):
    __tablename__ = 'document_processing_jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    submission_id: Mapped[str] = mapped_column(ForeignKey('academic_submissions.id'), index=True)
    requested_by: Mapped[str] = mapped_column(String(254), index=True)
    input_hash: Mapped[str] = mapped_column(String(64), unique=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default='queued', index=True)
    stage: Mapped[str] = mapped_column(String(24), default='queued')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    error_class: Mapped[str] = mapped_column(String(40), default='')
    error: Mapped[str] = mapped_column(Text, default='')
    model: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(80))
    context: Mapped[dict] = mapped_column(JSON)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)

class DocumentInterpretation(Base):
    __tablename__ = 'document_interpretations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    submission_id: Mapped[str] = mapped_column(ForeignKey('academic_submissions.id'), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('document_processing_jobs.id'), unique=True)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class InterpretationCorrection(Base):
    __tablename__ = 'interpretation_corrections'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    interpretation_id: Mapped[str] = mapped_column(ForeignKey('document_interpretations.id'), index=True)
    reviewer: Mapped[str] = mapped_column(String(254))
    result: Mapped[dict] = mapped_column(JSON)
    confirmed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class InterpretationCache(Base):
    __tablename__ = 'document_interpretation_cache'
    input_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class AssignmentBrief(Base):
    __tablename__ = 'assignment_briefs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assignment_id: Mapped[str] = mapped_column(ForeignKey('academic_assignments.id'), index=True)
    file_path: Mapped[str] = mapped_column(String(500))
    file_name: Mapped[str] = mapped_column(String(255))
    structure: Mapped[dict] = mapped_column(JSON)
    proposed_questions: Mapped[list] = mapped_column(JSON, default=list)
    approved_questions: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
