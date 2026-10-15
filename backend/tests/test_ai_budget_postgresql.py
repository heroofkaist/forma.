"""Opt-in multi-connection PostgreSQL race, in a new disposable test schema."""
import os
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
import ai_budget
from budget_models import AIRequestCharge
from migrations import apply_migrations
from persistence import (Base, _normalize_database_url, AcademicCourse, CourseOffering,
                         AssignmentFamily, AcademicAssignment, AcademicSubmission)
from processing_models import ProcessingJob


def test_postgresql_last_allowance_race_and_migration(monkeypatch):
    url = os.getenv('FORMA_TEST_POSTGRESQL_URL')
    if not url: pytest.skip('Set a dedicated safe FORMA_TEST_POSTGRESQL_URL for a multi-connection budget race.')
    schema = 'forma_budget_test_' + uuid4().hex
    root = create_engine(_normalize_database_url(url))
    scoped = None
    try:
        with root.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        scoped = create_engine(_normalize_database_url(url), connect_args={'options': '-csearch_path=' + schema})
        Base.metadata.create_all(scoped); apply_migrations(scoped); apply_migrations(scoped)
        factory = sessionmaker(scoped, expire_on_commit=False)
        with factory() as db:
            course = AcademicCourse(code='BUDGET', name='Synthetic', instructor='Synthetic', department='Science'); db.add(course); db.flush()
            offering = CourseOffering(course_id=course.id, academic_year='2026', term='Fall', section='01', class_code='BUDGET-SYNTHETIC'); db.add(offering)
            family = AssignmentFamily(course_id=course.id, title='Synthetic'); db.add(family); db.flush()
            assignment = AcademicAssignment(offering_id=offering.id, family_id=family.id, title='Synthetic'); db.add(assignment); db.flush()
            submission = AcademicSubmission(assignment_id=assignment.id, student_id='synthetic', student_name='Synthetic', file_path='unused.pdf', file_name='unused.pdf', file_type='pdf'); db.add(submission); db.flush()
            jobs = []
            for i in range(2):
                job = ProcessingJob(submission_id=submission.id, requested_by='synthetic', input_hash=str(i)*64, content_hash='a'*64, model='synthetic', prompt_version='test', context={})
                db.add(job); db.flush(); jobs.append(job.id)
            db.commit()
        monkeypatch.setattr(ai_budget, 'SessionLocal', factory)
        monkeypatch.setenv('FORMA_AI_PAID_ENABLED', 'true'); monkeypatch.setenv('FORMA_AI_MONTHLY_BUDGET_USD', '0.02')
        def compete(job):
            try: return ai_budget.reserve(job, 'openrouter', 'synthetic', 1_000_000)
            except ai_budget.BudgetUnavailable: return None
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(compete, jobs))
        assert sum(r is not None for r in results) == 1
        with factory() as db: assert len(db.scalars(select(AIRequestCharge)).all()) == 1
    finally:
        if scoped: scoped.dispose()
        with root.begin() as connection: connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        root.dispose()
