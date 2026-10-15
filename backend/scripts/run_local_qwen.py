"""Serve only a benchmark's isolated SQLite runtime, overriding inherited env."""
import argparse
import os
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-file', required=True, type=Path)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--frontend-origin', default='http://localhost:3000')
    parser.add_argument('--review-only', action='store_true', help='Disable processing workers and point new local requests at an unused loopback port; use saved results only.')
    args = parser.parse_args()
    runtime = args.runtime_file.resolve(); values = dotenv_values(runtime)
    root = runtime.parent
    if values.get('FORMA_DATABASE_URL') != 'sqlite:///' + str(root / 'benchmark.sqlite3'):
        raise SystemExit('Only an isolated benchmark.sqlite3 database is accepted.')
    if values.get('FORMA_STORAGE_DIR') != str(root / 'storage') or not (root / 'benchmark.sqlite3').exists():
        raise SystemExit('Expected existing isolated benchmark storage/database.')
    origin = urlsplit(args.frontend_origin)
    if origin.scheme != 'http' or origin.hostname not in {'localhost', '127.0.0.1'} or origin.path or origin.query or origin.fragment or origin.username:
        raise SystemExit('A plain loopback frontend origin is required.')
    os.environ.update({key: value for key, value in values.items() if value is not None})
    os.environ.update({'FORMA_AI_PROVIDER': 'ollama', 'FORMA_LOAD_ENV_FILE': 'false',
        'FORMA_STORAGE_BACKEND': 'local', 'FORMA_EMAIL_WORKER_ENABLED': 'false', 'FORMA_PUBLIC_REGISTRATION': 'false',
        'FORMA_LEGACY_LOGIN_ENABLED': 'false', 'FORMA_AI_PAID_ENABLED': 'false', 'FORMA_OPENROUTER_API_KEY': '', 'GEMINI_API_KEY': '', 'FORMA_SMTP_HOST': '',
        'FRONTEND_ORIGIN': args.frontend_origin, 'FORMA_DOCUMENT_WORKER_ENABLED': 'true', 'FORMA_DOCUMENT_CONCURRENCY': '1'})
    if args.review_only:
        os.environ.update({'FORMA_DOCUMENT_WORKER_ENABLED': 'false', 'FORMA_OLLAMA_BASE_URL': 'http://127.0.0.1:9'})
    import uvicorn
    uvicorn.run('main:app', host='127.0.0.1', port=args.port)


if __name__ == '__main__': main()
