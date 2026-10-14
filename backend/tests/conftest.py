"""Never inherit live Neon/R2/provider configuration during test collection.

PostgreSQL integration tests separately use an isolated transactional schema via
an explicitly configured FORMA_TEST_POSTGRESQL_URL.
"""
import atexit
import os
import shutil
import tempfile
from pathlib import Path

_test_root = Path(tempfile.mkdtemp(prefix="forma-test-suite-"))
os.environ["FORMA_DATABASE_URL"] = f"sqlite:///{_test_root / 'suite.sqlite3'}"
os.environ["FORMA_STORAGE_BACKEND"] = "local"
os.environ["FORMA_AUTH_REQUIRED"] = "false"
os.environ["FRONTEND_ORIGIN"] = "http://localhost:3000"
os.environ["FORMA_DEMO_MODE"] = "true"
os.environ["FORMA_PUBLIC_REGISTRATION"] = "false"
os.environ["FORMA_EMAIL_WORKER_ENABLED"] = "false"
os.environ["GEMINI_API_KEY"] = ""
os.environ["FORMA_SMTP_HOST"] = ""

import persistence
persistence.STORAGE_DIR = _test_root / "storage"
persistence.STORAGE_DIR.mkdir()


def cleanup():
    persistence.engine.dispose()
    shutil.rmtree(_test_root, ignore_errors=True)

atexit.register(cleanup)
