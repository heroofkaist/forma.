"""Roles and tenant metadata are additive; no existing identities are rewritten."""
from datetime import datetime
from uuid import uuid4
from sqlalchemy import String, ForeignKey, DateTime, JSON, Text, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from persistence import Base, now_utc

class AccountRole(Base):
    __tablename__ = 'account_roles'
    __table_args__ = (CheckConstraint("role IN ('student','teacher','school_admin','platform_admin')", name='account_role_allowed'),)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), primary_key=True)
    role: Mapped[str] = mapped_column(String(32), default='student')

class Institution(Base):
    __tablename__ = 'institutions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class InstitutionMembership(Base):
    __tablename__ = 'institution_memberships'
    __table_args__ = (UniqueConstraint('institution_id', 'account_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    institution_id: Mapped[str] = mapped_column(ForeignKey('institutions.id'), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), index=True)
    role: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default='active')

class CourseInstitution(Base):
    __tablename__ = 'course_institutions'
    course_id: Mapped[str] = mapped_column(ForeignKey('academic_courses.id'), primary_key=True)
    institution_id: Mapped[str] = mapped_column(ForeignKey('institutions.id'), index=True)

class TeacherInvitation(Base):
    __tablename__ = 'teacher_invitations'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), index=True)
    institution_id: Mapped[str] = mapped_column(ForeignKey('institutions.id'))
    invited_by: Mapped[str] = mapped_column(ForeignKey('accounts.id'))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class AuditEvent(Base):
    __tablename__ = 'audit_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor: Mapped[str] = mapped_column(String(254))
    action: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
