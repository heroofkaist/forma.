"""Synthetic-only local benchmark: isolated accounts -> PDF upload -> worker -> review.

Never imports .env or reuses an existing database. Raw outputs are saved only for
PDFs generated below. No arbitrary input path or production URL is accepted.
"""
import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import threading
import time


def make_pdf(path):
    import pymupdf
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    pdf = pymupdf.open()
    first = pdf.new_page()
    first.insert_text((45, 60), 'Question 1: Newton\'s second law\nm = 2 kg, F = 6 N.\nF = ma\na = F / m = 3 m/s^2\nThe solution continues on page 2.', fontsize=16)
    # A diagram on a page which ALSO has selectable text.
    first.draw_rect(pymupdf.Rect(160, 210, 290, 300), color=(0, 0, 0), width=2)
    first.draw_line((290, 255), (420, 255), color=(0, 0, 0), width=3)
    first.draw_line((400, 244), (420, 255), width=2); first.draw_line((400, 266), (420, 255), width=2)
    first.insert_text((180, 250), '2 kg', fontsize=18); first.insert_text((330, 238), 'F = 6 N', fontsize=16)
    image = Image.new('RGB', (1100, 1400), 'white'); draw = ImageDraw.Draw(image)
    font_path = Path('/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf')
    font = ImageFont.truetype(str(font_path), 44) if font_path.exists() else ImageFont.load_default(size=38)
    draw.multiline_text((65, 100), 'Question 1 (continued)\nv = u + at\nu = 0, t = 4 s\nv = 0 + 3 x 4 = 12 m/s\nThe force points to the right.', font=font, fill='#12284d', spacing=22)
    draw.line((100, 700, 700, 700), fill='#12284d', width=4); draw.line((700, 700, 680, 685), fill='#12284d', width=4)
    draw.text((180, 760), 'motion to the right', font=font, fill='#12284d')
    stream = io.BytesIO(); image.save(stream, format='PNG')
    second = pdf.new_page(); second.insert_image(second.rect, stream=stream.getvalue())
    third = pdf.new_page()
    third.insert_text((45, 60), 'Question 2: Energy and an inclined plane\nE_k = (1/2) m v^2\nm = 2 kg, v = 3 m/s\nE_k = 9 J', fontsize=16)
    third.draw_line((80, 550), (430, 550), width=2); third.draw_line((80, 550), (430, 330), width=3)
    third.draw_rect(pymupdf.Rect(240, 405, 300, 455), color=(0, 0, 0), width=2)
    third.draw_line((270, 430), (270, 520), width=3); third.insert_text((280, 510), 'mg', fontsize=18)
    third.insert_text((300, 380), 'inclined plane', fontsize=14)
    # Deliberately illegible patch: a model should not invent its contents.
    patch = Image.new('RGB', (500, 90), 'white'); ImageDraw.Draw(patch).text((10, 10), 'blurred unresolved work', fill='black', font=font)
    patch = patch.filter(ImageFilter.GaussianBlur(10)); raw = io.BytesIO(); patch.save(raw, format='PNG')
    third.insert_image(pymupdf.Rect(50, 650, 500, 735), stream=raw.getvalue())
    pdf.save(path); pdf.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path, help='A new synthetic-only directory; existing database is refused.')
    args = parser.parse_args(); root = args.output.resolve(); root.mkdir(parents=True, exist_ok=True)
    database = root / 'benchmark.sqlite3'
    if database.exists(): raise SystemExit('Refusing to reuse an existing benchmark database; choose a new --output directory.')
    os.environ.update({'FORMA_DATABASE_URL': 'sqlite:///' + str(database), 'FORMA_STORAGE_BACKEND': 'local',
        'FORMA_STORAGE_DIR': str(root / 'storage'), 'FORMA_AUTH_REQUIRED': 'true',
        'FORMA_AUTH_SECRET': 'synthetic-local-only-secret-at-least-32-bytes', 'FORMA_DEMO_MODE': 'false',
        'FORMA_LEGACY_LOGIN_ENABLED': 'false', 'FORMA_PUBLIC_REGISTRATION': 'false',
        'FORMA_SMTP_HOST': '', 'FORMA_EMAIL_WORKER_ENABLED': 'false', 'FORMA_DOCUMENT_WORKER_ENABLED': 'false',
        'FORMA_AI_PAID_ENABLED': 'false', 'FORMA_OPENROUTER_API_KEY': '', 'GEMINI_API_KEY': '', 'FORMA_LOAD_ENV_FILE': 'false', 'FORMA_AI_PROVIDER': 'ollama', 'FRONTEND_ORIGIN': 'http://localhost:3000'})
    # This file contains ONLY isolated synthetic runtime settings, no .env keys.
    runtime_keys = ['FORMA_DATABASE_URL', 'FORMA_STORAGE_BACKEND', 'FORMA_STORAGE_DIR', 'FORMA_AUTH_REQUIRED',
        'FORMA_AUTH_SECRET', 'FORMA_DEMO_MODE', 'FORMA_LEGACY_LOGIN_ENABLED', 'FORMA_PUBLIC_REGISTRATION',
        'FORMA_SMTP_HOST', 'FORMA_EMAIL_WORKER_ENABLED', 'FORMA_LOAD_ENV_FILE', 'GEMINI_API_KEY', 'FORMA_AI_PROVIDER', 'FRONTEND_ORIGIN']
    (root / 'runtime.env').write_text('\n'.join(f'{key}={os.environ[key]}' for key in runtime_keys)
        + '\nFORMA_DOCUMENT_WORKER_ENABLED=true\nFORMA_DOCUMENT_CONCURRENCY=1\nFORMA_OLLAMA_BASE_URL=http://127.0.0.1:11434\nFORMA_OLLAMA_MODEL=qwen3-vl:8b-instruct\n')
    from fastapi.testclient import TestClient
    import httpx
    import persistence
    from account_models import Account
    from institution_models import AccountRole, Institution, InstitutionMembership
    from accounts import hasher
    from main import app
    import document_processing
    from services.ai_providers.engine import interpret_document, configuration
    import platform
    pdf_path = root / 'synthetic-three-pages.pdf'; make_pdf(pdf_path)
    raw_responses = []
    def observed(*args, **kwargs):
        return interpret_document(*args, **kwargs, observe=raw_responses.append)
    document_processing.interpret_document = observed
    samples = []; stop = threading.Event()
    def sample():
        while not stop.is_set():
            try:
                output = subprocess.check_output(['ps', '-axo', 'rss,comm'], text=True)
                rss = sum(int(line.split()[0]) * 1024 for line in output.splitlines()[1:] if 'ollama' in line.lower())
                with httpx.Client(trust_env=False, timeout=2) as client:
                    ps = client.get(configuration().options['base_url'] + '/api/ps').json()
                samples.append({'seconds': round(time.monotonic() - began, 3), 'ollama_process_rss_bytes': rss,
                    'models': [{k: m[k] for k in ('name', 'size', 'size_vram', 'context_length') if k in m} for m in ps.get('models', [])]})
            except Exception: pass  # Monitoring is best-effort, never fabricated.
            stop.wait(1)
    result = {'provider': 'ollama', 'config': configuration().__dict__, 'platform': platform.platform(), 'synthetic_only': True}
    with TestClient(app) as client:
        with persistence.SessionLocal() as db:
            institution = Institution(name='Synthetic local benchmark'); db.add(institution); db.flush()
            accounts = []
            for role in ('teacher', 'student'):
                account = Account(email=f'local-{role}@example.test', display_name=f'Synthetic {role}', verified=True,
                    password_hash=hasher.hash('Forma-local-benchmark-only-123'))
                db.add(account); db.flush(); db.add(AccountRole(account_id=account.id, role=role)); accounts.append(account)
            db.add(InstitutionMembership(institution_id=institution.id, account_id=accounts[0].id, role='teacher'))
            db.commit(); institution_id = institution.id
        def headers(role):
            response = client.post('/api/auth/login', json={'role': role, 'username': f'local-{role}@example.test', 'password': 'Forma-local-benchmark-only-123'})
            response.raise_for_status(); return {'Authorization': 'Bearer ' + response.json()['access_token']}
        teacher, student = headers('teacher'), headers('student')
        course = client.post('/api/courses', headers=teacher, json={'institution_id': institution_id, 'title': 'Synthetic physics', 'code': 'LOCAL-QWEN', 'subject': 'Physics', 'academic_year': '2026', 'term': 'Fall'})
        course.raise_for_status(); course = course.json()
        joined = client.post('/api/enrollment/join', headers=student, json={'class_code': course['class_code']}); joined.raise_for_status()
        assignment = client.post('/academic/assignments', headers=teacher, json={'offering_id': course['offering_id'], 'title': 'Synthetic multimodal benchmark', 'assignment_type': 'problem_set', 'originality_enabled': False,
            'questions': [{'id': 'q1', 'title': 'Question 1', 'statement': 'Explain acceleration and continuation to velocity.', 'maximum_points': 1}, {'id': 'q2', 'title': 'Question 2', 'statement': 'Describe energy and the inclined-plane diagram.', 'maximum_points': 1}]})
        assignment.raise_for_status()
        receipt = client.post('/academic/assignments/' + assignment.json()['id'] + '/submissions', headers=student, files={'file': (pdf_path.name, pdf_path.read_bytes(), 'application/pdf')}); receipt.raise_for_status()
        sid = receipt.json()['id']; result['submission_id'] = sid
        began = time.monotonic(); thread = threading.Thread(target=sample, daemon=True); thread.start()
        try: result['processed'] = document_processing.process_one()
        finally: stop.set(); thread.join(timeout=4)
        result['wall_seconds'] = round(time.monotonic() - began, 3)
        status = client.get('/api/document-analysis/' + sid + '/status', headers=teacher); status.raise_for_status(); result['jobs'] = status.json()['jobs']
        review = client.get('/api/document-analysis/' + sid, headers=teacher); review.raise_for_status(); result['review'] = review.json()
        original = client.get('/api/submission-files/' + sid, headers=teacher)
        result['original_pdf_match'] = original.status_code == 200 and original.content == pdf_path.read_bytes()
        result['schema_valid'] = bool(result['review']['items'])
    from services.ai_providers.ollama import PageObservations
    validity = []
    for raw in raw_responses:
        try:
            PageObservations.model_validate_json(raw.get('message', {}).get('content', ''))
            validity.append(True)
        except ValueError:
            validity.append(False)
    result['raw_schema_validity'] = validity
    result['fixture_pages'] = {'1': 'Typed mathematics plus embedded vector force diagram',
        '2': 'Generated handwriting-style equations and continuation of question 1',
        '3': 'Typed energy solution, inclined-plane diagram and deliberately blurred image patch'}
    (root / 'raw-responses.json').write_text(json.dumps(raw_responses, indent=2, ensure_ascii=False))
    (root / 'memory-samples.json').write_text(json.dumps(samples, indent=2))
    result['peak_ollama_process_rss_bytes'] = max((s['ollama_process_rss_bytes'] for s in samples), default=None)
    (root / 'report.json').write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(json.dumps({'output': str(root), 'status': result['jobs'][0]['status'], 'schema_valid': result['schema_valid'], 'wall_seconds': result['wall_seconds'], 'peak_ollama_process_rss_bytes': result['peak_ollama_process_rss_bytes']}))
    if not result['schema_valid']: raise SystemExit(1)


if __name__ == '__main__': main()
