"""Additive paid-inference accounting; no prompts, images, keys or identities."""
from datetime import datetime
from uuid import uuid4
from sqlalchemy import String, BigInteger, Integer, DateTime, Boolean, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from persistence import Base, now_utc


class AIBudgetPeriod(Base):
    __tablename__ = 'ai_budget_periods'
    month: Mapped[str] = mapped_column(String(7), primary_key=True)
    limit_nusd: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AIBudgetControl(Base):
    __tablename__ = 'ai_budget_controls'
    provider: Mapped[str] = mapped_column(String(24), primary_key=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(String(40), default='')
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AIRequestCharge(Base):
    __tablename__ = 'ai_request_charges'
    __table_args__ = (CheckConstraint('reserved_nusd > 0', name='ai_positive_reservation'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[str] = mapped_column(ForeignKey('document_processing_jobs.id'), index=True)
    provider: Mapped[str] = mapped_column(String(24))
    model: Mapped[str] = mapped_column(String(120))
    billing_month: Mapped[str] = mapped_column(String(7), index=True)
    billed_month: Mapped[str | None] = mapped_column(String(7), nullable=True)
    state: Mapped[str] = mapped_column(String(16), default='in_flight', index=True)
    reserved_nusd: Mapped[int] = mapped_column(BigInteger)
    job_limit_nusd: Mapped[int] = mapped_column(BigInteger)
    actual_nusd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actual_usd: Mapped[str | None] = mapped_column(String(80), nullable=True)
    generation_id: Mapped[str | None] = mapped_column(String(160), nullable=True, unique=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
