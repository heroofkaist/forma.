"""Reviewed additive migrations, run under a PostgreSQL advisory transaction lock."""
def apply_migrations(bind):
    from sqlalchemy import select
    from sqlalchemy.engine import Connection
    from contextlib import nullcontext
    from account_models import SchemaMigration
    import document_models
    from persistence import Base
    names = ("accounts", "account_sessions", "account_actions", "account_rate_buckets",
             "course_owners", "offering_policies", "enrollment_states", "assignment_owners")
    with (nullcontext(bind) if isinstance(bind, Connection) else bind.begin()) as connection:
        if connection.dialect.name == "postgresql":
            connection.exec_driver_sql("SELECT pg_advisory_xact_lock(62401701)")
        SchemaMigration.__table__.create(connection, checkfirst=True)
        version = "001_public_accounts_course_ownership"
        for version, tables in ((version, names), ("002_structured_documents_materials", ("submission_documents", "course_materials")), ("003_document_review_history", ("document_reviews", "published_document_reviews")), ("004_durable_email_outbox", ("email_outbox",))):
            if connection.scalar(select(SchemaMigration.version).where(SchemaMigration.version == version)):
                continue
            for name in tables:
                Base.metadata.tables[name].create(connection, checkfirst=True)
            connection.execute(SchemaMigration.__table__.insert().values(version=version))
