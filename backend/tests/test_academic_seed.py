from contextlib import contextmanager
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import academic_api
from persistence import (
    AcademicAssignment,
    AcademicCourse,
    AcademicSubmission,
    Assignment,
    AssignmentFamily,
    CourseEnrollment,
    CourseOffering,
    Submission,
    _normalize_database_url,
    init_db,
)


@contextmanager
def _isolated_connection(postgresql_url: str | None = None):
    if postgresql_url:
        engine = create_engine(_normalize_database_url(postgresql_url))
        connection = engine.connect()
        transaction = connection.begin()
        schema = f"forma_seed_test_{uuid4().hex}"
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
    else:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        connection = engine.connect()
        transaction = connection.begin()

    try:
        yield connection
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()


def _assert_seed_is_idempotent(
    connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = sessionmaker(bind=connection, expire_on_commit=False)
    blobs: dict[str, bytes] = {}
    monkeypatch.setattr(academic_api, "SessionLocal", factory)
    monkeypatch.setattr(academic_api, "DEMO_MODE", True)
    monkeypatch.setattr(academic_api, "blob_exists", lambda key: key in blobs)
    monkeypatch.setattr(
        academic_api,
        "write_blob",
        lambda key, body: blobs.__setitem__(key, body),
    )
    monkeypatch.setattr(academic_api, "read_blob", lambda key: blobs[key])

    init_db(connection, factory)
    with factory() as db:
        db.add(
            AcademicCourse(
                id="existing-course-preserved",
                code="CHEM100",
                name="Existing course",
                instructor="Existing instructor",
                department="Chemistry",
            )
        )
        db.add(
            AcademicCourse(
                id=academic_api.COURSE_ID,
                code="PHY101",
                name="General Physics I",
                instructor="Existing instructor",
                department="Physics",
            )
        )
        db.flush()
        db.add(
            AssignmentFamily(
                id=academic_api.FAMILY_ID,
                course_id=academic_api.COURSE_ID,
                title="Forces on an Incline",
            )
        )
        for year, offering_id in academic_api.OFFERING_IDS.items():
            db.add(
                CourseOffering(
                    id=offering_id,
                    course_id=academic_api.COURSE_ID,
                    academic_year=year,
                    term="Fall",
                    section="01",
                    status="active",
                    class_code=f"PHY101-F{year[-2:]}",
                )
            )
        db.flush()
        db.add(
            AcademicAssignment(
                id=academic_api.ASSIGNMENT_IDS["2024"],
                offering_id=academic_api.OFFERING_IDS["2024"],
                family_id=academic_api.FAMILY_ID,
                legacy_assignment_id=None,
                title="Existing saved title",
            )
        )
        db.commit()

    init_db(connection, factory)
    academic_api.ensure_academic_seed()
    academic_api.ensure_academic_seed()
    init_db(connection, factory)

    with factory() as db:
        assignments = db.scalars(
            select(AcademicAssignment).where(
                AcademicAssignment.id.in_(academic_api.ASSIGNMENT_IDS.values())
            )
        ).all()
        assert len(assignments) == 3
        for academic_assignment in assignments:
            legacy = db.get(Assignment, academic_assignment.legacy_assignment_id)
            assert legacy is not None
            assert legacy.id == f"legacy-{academic_assignment.id}"

        submissions = db.scalars(
            select(AcademicSubmission).where(
                AcademicSubmission.id.in_(academic_api.SEED_SUBMISSION_IDS.values())
            )
        ).all()
        assert len(submissions) == 2
        for academic_submission in submissions:
            legacy_submission = db.get(
                Submission, academic_submission.legacy_submission_id
            )
            assert legacy_submission is not None
            assert len(legacy_submission.id) <= 36
            assert db.get(Assignment, legacy_submission.assignment_id) is not None

        assert db.scalar(
            select(func.count()).select_from(Assignment).where(
                Assignment.id.in_(
                    [
                        f"legacy-{assignment_id}"
                        for assignment_id in academic_api.ASSIGNMENT_IDS.values()
                    ]
                )
            )
        ) == 3
        assert db.scalar(
            select(func.count()).select_from(CourseEnrollment).where(
                CourseEnrollment.offering_id.in_(academic_api.OFFERING_IDS.values()),
                CourseEnrollment.student_id == academic_api.DEMO_STUDENT_ID,
            )
        ) == 3
        assert db.get(AcademicCourse, "existing-course-preserved") is not None
        assert db.get(AcademicCourse, academic_api.COURSE_ID).instructor == (
            "Existing instructor"
        )


def test_academic_demo_seed_is_idempotent_with_foreign_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _isolated_connection() as connection:
        _assert_seed_is_idempotent(connection, monkeypatch)


@pytest.mark.skipif(
    not os.getenv("FORMA_TEST_POSTGRESQL_URL"),
    reason="Set FORMA_TEST_POSTGRESQL_URL to run the PostgreSQL integration regression test.",
)
def test_academic_demo_seed_preserves_postgresql_foreign_key_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _isolated_connection(os.environ["FORMA_TEST_POSTGRESQL_URL"]) as connection:
        _assert_seed_is_idempotent(connection, monkeypatch)


def test_production_does_not_seed_academic_demo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _isolated_connection() as connection:
        factory = sessionmaker(bind=connection, expire_on_commit=False)
        monkeypatch.setattr(academic_api, "SessionLocal", factory)
        monkeypatch.setattr(academic_api, "DEMO_MODE", False)
        init_db(connection, factory)

        academic_api.ensure_academic_seed()

        with factory() as db:
            assert db.get(AcademicCourse, academic_api.COURSE_ID) is None


@pytest.mark.parametrize("postgresql", [False, True])
def test_account_migrations_preserve_existing_records_and_repeat(monkeypatch, postgresql):
    from account_models import SchemaMigration
    from migrations import apply_migrations
    if postgresql and not os.getenv("FORMA_TEST_POSTGRESQL_URL"):
        pytest.skip("Set FORMA_TEST_POSTGRESQL_URL for additive PostgreSQL migration validation.")
    with _isolated_connection(os.getenv("FORMA_TEST_POSTGRESQL_URL") if postgresql else None) as connection:
        factory = sessionmaker(bind=connection, expire_on_commit=False)
        init_db(connection, factory)
        with factory() as db:
            db.add(AcademicCourse(id="preserved-chemistry", code="CHEM101", name="Chemistry", instructor="Existing Teacher", department="Science"))
            db.commit()
        apply_migrations(connection)
        apply_migrations(connection)
        init_db(connection, factory)
        with factory() as db:
            assert db.get(AcademicCourse, "preserved-chemistry").name == "Chemistry"
            assert len(db.scalars(select(SchemaMigration)).all()) == 11
