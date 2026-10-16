"""Reviewed additive migrations, run under a PostgreSQL advisory transaction lock."""
def apply_migrations(bind):
    from sqlalchemy import inspect, select
    from sqlalchemy.engine import Connection
    from contextlib import nullcontext
    from account_models import SchemaMigration
    import document_models
    import institution_models
    import processing_models
    import budget_models
    import assessment_models
    import review_pilot_models
    import comparison_models
    import integrity_models
    import course_archive_models
    from persistence import Base
    names = ("accounts", "account_sessions", "account_actions", "account_rate_buckets",
             "course_owners", "offering_policies", "enrollment_states", "assignment_owners")
    with (nullcontext(bind) if isinstance(bind, Connection) else bind.begin()) as connection:
        if connection.dialect.name == "postgresql":
            connection.exec_driver_sql("SELECT pg_advisory_xact_lock(62401701)")
        SchemaMigration.__table__.create(connection, checkfirst=True)
        # Separate additive versions; no existing rubric, grade or source is rewritten.
        version = "001_public_accounts_course_ownership"
        for version, tables in ((version, names), ("002_structured_documents_materials", ("submission_documents", "course_materials")), ("003_document_review_history", ("document_reviews", "published_document_reviews")), ("004_durable_email_outbox", ("email_outbox",)), ("005_institution_roles", ("account_roles", "institutions", "institution_memberships", "course_institutions", "teacher_invitations", "audit_events")), ("006_document_understanding_jobs", ("document_processing_jobs", "document_interpretations", "interpretation_corrections", "document_interpretation_cache", "assignment_briefs")), ("007_submission_student_id_width", ()), ("008_ai_budget_ledger", ("ai_budget_periods", "ai_budget_controls", "ai_request_charges"))):
            if connection.scalar(select(SchemaMigration.version).where(SchemaMigration.version == version)):
                continue
            for name in tables:
                Base.metadata.tables[name].create(connection, checkfirst=True)
            if version == "007_submission_student_id_width" and connection.dialect.name == "postgresql":
                column = next(column for column in inspect(connection).get_columns("submissions") if column["name"] == "anonymous_student_id")
                # Never narrow a manually widened column (including unbounded TEXT).
                length = getattr(column["type"], "length", None)
                if length is not None and length < 64:
                    connection.exec_driver_sql("ALTER TABLE submissions ALTER COLUMN anonymous_student_id TYPE VARCHAR(64)")
            connection.execute(SchemaMigration.__table__.insert().values(version=version))
        version = '009_rubric_assessment'
        if not connection.scalar(select(SchemaMigration.version).where(SchemaMigration.version == version)):
            for name in ('assessment_rubrics', 'assessment_suggestions', 'assessment_decisions'):
                Base.metadata.tables[name].create(connection, checkfirst=True)
            connection.execute(SchemaMigration.__table__.insert().values(version=version))

        version = "010_originality_execution_receipts"
        if not connection.scalar(select(SchemaMigration.version).where(SchemaMigration.version == version)):
            Base.metadata.tables["academic_originality_analyses"].create(connection, checkfirst=True)
            connection.execute(SchemaMigration.__table__.insert().values(version=version))

        version = "011_guardian_registration"
        if not connection.scalar(select(SchemaMigration.version).where(SchemaMigration.version == version)):
            Base.metadata.tables["guardian_registrations"].create(connection, checkfirst=True)
            connection.execute(SchemaMigration.__table__.insert().values(version=version))

        version = "012_review_pilot"
        if not connection.scalar(select(SchemaMigration.version).where(SchemaMigration.version == version)):
            for name in ('review_decision_cards', 'review_question_page_maps', 'submission_upload_receipts'):
                Base.metadata.tables[name].create(connection, checkfirst=True)
            connection.execute(SchemaMigration.__table__.insert().values(version=version))

        version = "013_local_comparison"
        if not connection.scalar(select(SchemaMigration.version).where(SchemaMigration.version == version)):
            Base.metadata.tables['assignment_comparisons'].create(connection, checkfirst=True)
            connection.execute(SchemaMigration.__table__.insert().values(version=version))

        version = "014_document_integrity_profiles"
        if not connection.scalar(select(SchemaMigration.version).where(SchemaMigration.version == version)):
            Base.metadata.tables['document_integrity_reports'].create(connection, checkfirst=True)
            connection.execute(SchemaMigration.__table__.insert().values(version=version))

        version = "015_shared_course_archive"
        if not connection.scalar(select(SchemaMigration.version).where(SchemaMigration.version == version)):
            for name in ("course_archive_links", "originality_corpus_snapshots"):
                Base.metadata.tables[name].create(connection, checkfirst=True)
            connection.execute(SchemaMigration.__table__.insert().values(version=version))
