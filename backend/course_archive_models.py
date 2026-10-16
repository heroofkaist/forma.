"""Optional course catalogue aliases and current immutable similarity generations."""
from datetime import datetime
from sqlalchemy import ForeignKey, String, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from persistence import Base, now_utc

class CourseArchiveLink(Base):
    __tablename__ = 'course_archive_links'
    course_id: Mapped[str] = mapped_column(ForeignKey('academic_courses.id'), primary_key=True)
    archive_key: Mapped[str] = mapped_column(String(80), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class OriginalityCorpusSnapshot(Base):
    __tablename__ = 'originality_corpus_snapshots'
    submission_id: Mapped[str] = mapped_column(ForeignKey('academic_submissions.id'), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    report_ids: Mapped[list] = mapped_column(JSON, default=list)
