"""Preserve historical IDs while accepting authenticated 36-character UUIDs."""
import os
from uuid import uuid4
import pytest
from sqlalchemy import inspect, select
from sqlalchemy.orm import sessionmaker
from migrations import apply_migrations
from persistence import Base, Assignment, Submission
from account_models import SchemaMigration
from test_academic_seed import _isolated_connection

VERSION = '007_submission_student_id_width'


@pytest.mark.parametrize('existing_width', [None, 24, 64, 128])
def test_student_uuid_roundtrip_and_idempotent_width_migration(existing_width):
    postgresql = existing_width is not None
    url = os.getenv('FORMA_TEST_POSTGRESQL_URL') if postgresql else None
    if postgresql and not url:
        pytest.skip('Set FORMA_TEST_POSTGRESQL_URL for isolated PostgreSQL width migration tests.')
    assert Submission.__table__.c.anonymous_student_id.type.length == 64
    with _isolated_connection(url) as connection:
        Base.metadata.create_all(connection)
        if postgresql:
            connection.exec_driver_sql(f'ALTER TABLE submissions ALTER COLUMN anonymous_student_id TYPE VARCHAR({existing_width})')
        factory = sessionmaker(bind=connection, expire_on_commit=False)
        with factory() as db:
            assignment = Assignment(title='Synthetic legacy assignment')
            db.add(assignment); db.flush()
            historical = Submission(assignment_id=assignment.id, student_name='Historical', anonymous_student_id='S-123', source_path='private/existing.pdf', page_count=3)
            db.add(historical); db.commit()
            historical_id, assignment_id = historical.id, assignment.id
        before = connection.execute(select(Submission.__table__)).mappings().all()
        apply_migrations(connection)
        apply_migrations(connection)
        assert connection.execute(select(Submission.__table__)).mappings().all() == before
        assert connection.scalar(select(SchemaMigration.version).where(SchemaMigration.version == VERSION)) == VERSION
        if postgresql:
            column = next(c for c in inspect(connection).get_columns('submissions') if c['name'] == 'anonymous_student_id')
            assert column['type'].length == max(64, existing_width)
        student_id = str(uuid4())
        assert len(student_id) == 36
        with factory() as db:
            submission = Submission(assignment_id=assignment_id, student_name=student_id, anonymous_student_id=student_id, source_path='private/student.pdf', page_count=4)
            db.add(submission); db.commit(); submission_id = submission.id
        with factory() as db:
            assert db.get(Submission, submission_id).anonymous_student_id == student_id
            assert db.get(Submission, historical_id).anonymous_student_id == 'S-123'
