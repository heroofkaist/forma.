"""Run only with the explicit safe test URL; never use production credentials."""
import os
from datetime import timedelta
import pytest
from sqlalchemy.orm import sessionmaker
from test_academic_seed import _isolated_connection
from persistence import init_db, AcademicCourse, CourseOffering, AssignmentFamily, AcademicAssignment, AcademicSubmission, now_utc
from migrations import apply_migrations
from processing_models import ProcessingJob
import document_processing

@pytest.mark.parametrize('postgresql',[False,True])
def test_processing_claims_and_lease_recovery_with_database_semantics(monkeypatch,postgresql):
    if postgresql and not os.getenv('FORMA_TEST_POSTGRESQL_URL'):
        pytest.skip('Set FORMA_TEST_POSTGRESQL_URL for PostgreSQL job claim integration.')
    with _isolated_connection(os.getenv('FORMA_TEST_POSTGRESQL_URL') if postgresql else None) as connection:
        factory=sessionmaker(bind=connection,expire_on_commit=False)
        init_db(connection,factory);apply_migrations(connection)
        with factory() as db:
            course=AcademicCourse(code='TEST',name='Synthetic',instructor='Synthetic',department='Science');db.add(course);db.flush()
            offering=CourseOffering(course_id=course.id,academic_year='2026',term='Fall',section='01',class_code='TEST-SYNTHETIC');db.add(offering)
            family=AssignmentFamily(course_id=course.id,title='Synthetic');db.add(family);db.flush()
            assignment=AcademicAssignment(offering_id=offering.id,family_id=family.id,title='Synthetic');db.add(assignment);db.flush()
            submission=AcademicSubmission(assignment_id=assignment.id,student_id='synthetic',student_name='Synthetic',file_path='unused-synthetic.pdf',file_name='synthetic.pdf',file_type='pdf');db.add(submission);db.flush()
            job=ProcessingJob(submission_id=submission.id,requested_by='synthetic',input_hash='a'*64,content_hash='b'*64,model='synthetic',prompt_version='document-understanding-v1',context={});db.add(job);db.commit();job_id=job.id
        monkeypatch.setattr(document_processing,'SessionLocal',factory)
        monkeypatch.setenv('FORMA_DOCUMENT_CONCURRENCY','1')
        first=document_processing.claim();assert first and first[0]==job_id
        assert document_processing.claim() is None
        with factory() as db:
            job=db.get(ProcessingJob,job_id);job.lease_until=now_utc()-timedelta(seconds=1);db.commit()
        recovered=document_processing.claim();assert recovered and recovered[1]!=first[1]
        with factory() as db:assert db.get(ProcessingJob,job_id).attempts==2
