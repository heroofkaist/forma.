"""Immutable, course-private local comparison receipts."""
from datetime import datetime
from uuid import uuid4
from sqlalchemy import ForeignKey, String, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from persistence import Base, now_utc

class AssignmentComparison(Base):
    __tablename__ = 'assignment_comparisons'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda:str(uuid4()))
    assignment_id: Mapped[str] = mapped_column(ForeignKey('academic_assignments.id'), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    result: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
