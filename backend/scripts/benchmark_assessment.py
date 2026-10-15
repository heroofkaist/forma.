"""Real local-only Phase 4 workflow using generated public synthetic PDFs.

No external/private input accepted; refuses an existing database. Model suggestions
are saved as unverified drafts; simulated teacher actions test workflow, not quality.
"""
import argparse
import json
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); root = args.output.resolve(); root.mkdir(parents=True, exist_ok=True)
    database = root / 'benchmark.sqlite3'
    if database.exists(): raise SystemExit('Choose a new output directory; existing database refused.')
    settings = {'FORMA_DATABASE_URL': 'sqlite:///' + str(database), 'FORMA_STORAGE_BACKEND': 'local',
        'FORMA_STORAGE_DIR': str(root / 'storage'), 'FORMA_AUTH_REQUIRED': 'true',
        'FORMA_AUTH_SECRET': 'phase-four-synthetic-local-secret-at-least-32-bytes', 'FORMA_DEMO_MODE': 'false',
        'FORMA_LEGACY_LOGIN_ENABLED': 'false', 'FORMA_PUBLIC_REGISTRATION': 'false', 'FORMA_SMTP_HOST': '',
        'FORMA_EMAIL_WORKER_ENABLED': 'false', 'FORMA_DOCUMENT_WORKER_ENABLED': 'false', 'FORMA_LOAD_ENV_FILE': 'false',
        'FORMA_AI_PROVIDER': 'ollama', 'FORMA_AI_PAID_ENABLED': 'false', 'FORMA_AI_PAID_FALLBACK_ENABLED': 'false',
        'FORMA_OPENROUTER_API_KEY': '', 'GEMINI_API_KEY': '', 'FRONTEND_ORIGIN': 'http://localhost:3000',
        'FORMA_OLLAMA_BASE_URL': 'http://127.0.0.1:11434', 'FORMA_OLLAMA_MODEL': 'qwen3-vl:8b-instruct',
        'FORMA_DOCUMENT_CONCURRENCY': '1'}
    os.environ.update(settings)
    (root / 'runtime.env').write_text('\n'.join(f'{k}={v}' for k, v in settings.items()) + '\n')
    import pymupdf
    from fastapi.testclient import TestClient
    from sqlalchemy import select, func
    import persistence
    from persistence import AcademicGrade
    from account_models import Account
    from institution_models import AccountRole, Institution, InstitutionMembership
    from accounts import hasher
    from main import app
    import document_processing
    from services.ai_providers.engine import interpret_document
    from services.assessment import evaluate
    import services.assessment as assessment_service
    from scripts.assessment_fixtures import CASES, FUTURE_CASES
    raw = []; current = {}
    def observer(data): raw.append({'case': current['name'], 'stage': current['stage'], 'response': data})
    def understand(*args, **kwargs): return interpret_document(*args, **kwargs, observe=observer)
    def assess(*args, **kwargs): return evaluate(*args, **kwargs, observe=observer)
    document_processing.interpret_document = understand
    assessment_service.evaluate = assess
    report = {'synthetic_only': True, 'paid_calls': False, 'cases': [], 'future_unsupported_cases': FUTURE_CASES}
    with TestClient(app) as client:
        with persistence.SessionLocal() as db:
            institution = Institution(name='Phase 4 synthetic institution'); db.add(institution); db.flush()
            for role in ('teacher', 'student'):
                account = Account(email=f'local-{role}@example.test', display_name=f'Synthetic {role}', verified=True,
                    password_hash=hasher.hash('Forma-local-benchmark-only-123'))
                db.add(account); db.flush(); db.add(AccountRole(account_id=account.id, role=role))
                if role == 'teacher': db.add(InstitutionMembership(institution_id=institution.id, account_id=account.id, role='teacher'))
            db.commit(); institution_id = institution.id
        def checked(response):
            response.raise_for_status(); return response.json()
        def login(role):
            return {'Authorization': 'Bearer ' + checked(client.post('/api/auth/login', json={'role': role, 'username': f'local-{role}@example.test', 'password': 'Forma-local-benchmark-only-123'}))['access_token']}
        teacher, student = login('teacher'), login('student')
        course = checked(client.post('/api/courses', headers=teacher, json={'institution_id': institution_id, 'title': 'Universal synthetic assessment', 'code': 'PHASE4', 'subject': 'Interdisciplinary', 'academic_year': '2026', 'term': 'Fall'}))
        checked(client.post('/api/enrollment/join', headers=student, json={'class_code': course['class_code']}))
        for case in CASES:
            current.update(name=case['name'], stage='understanding')
            assignment = checked(client.post('/academic/assignments', headers=teacher, json={'offering_id': course['offering_id'], 'title': case['name'], 'assignment_type': case['category'], 'maximum_score': 5, 'description': case['instructions'], 'originality_enabled': False,
                'questions': [{'id': 'q1', 'title': 'Whole submission', 'statement': case['instructions'], 'maximum_points': 5,
                    'criteria': [{'id': 'reasoning', 'description': case['criterion'], 'maximum_points': 5}]}]}))
            pdf = pymupdf.open(); page = pdf.new_page(); page.insert_textbox(pymupdf.Rect(45, 45, 550, 780), case['text'], fontsize=12)
            data = pdf.tobytes(); pdf.close(); (root / (case['name'] + '.pdf')).write_bytes(data)
            submission = checked(client.post('/academic/assignments/' + assignment['id'] + '/submissions', headers=student, files={'file': (case['name'] + '.pdf', data, 'application/pdf')}))
            sid = submission['id']; path = '/api/assessment/' + sid
            start = time.monotonic(); document_processing.process_one(); understanding_seconds = time.monotonic() - start
            rubric_path = '/api/assessment-rubrics/' + assignment['id']
            candidate = checked(client.get(rubric_path, headers=teacher))['candidate']
            candidate['criteria'][0].update(performance_descriptions=case['performance'], insight_tag='reasoning')
            checked(client.post(rubric_path, headers=teacher, json=candidate))
            queued = client.post(path, headers=teacher, json={})
            record = {'name': case['name'], 'category': case['category'], 'expected': case['expected'], 'expected_finding': case['expected_finding'],
                'submission_id': sid, 'understanding_seconds': round(understanding_seconds, 3), 'request_status': queued.status_code}
            if queued.status_code == 202:
                current['stage'] = 'assessment'; start = time.monotonic(); document_processing.process_one()
                record['assessment_seconds'] = round(time.monotonic() - start, 3)
                result = checked(client.get(path, headers=teacher)); record['assessment'] = result
                if result['items']:
                    item = result['items'][0]; c = item['result']['criteria'][0]
                    record['finding_matches_expected'] = c['finding'] == case['expected_finding'] or (case['expected_finding'] == 'concern' and c['finding'] == 'mixed')
                    record['strict_validation_passed'] = True
                    # Simulated explicit teacher override proves no automatic publication.
                    decision = {'question_id': 'q1', 'criterion_id': 'reasoning', 'action': 'accepted', 'points': 3,
                        'feedback': 'Synthetic workflow check only; not a human quality endorsement.', 'finding': c['finding']}
                    record['teacher_override'] = checked(client.post(path + '/decisions', headers=teacher, json={'suggestion_id': item['id'], 'decisions': [decision]}))
                else: record['strict_validation_passed'] = False
            else: record['request_error'] = queued.json()
            with persistence.SessionLocal() as db: record['grade_rows'] = db.scalar(select(func.count()).select_from(AcademicGrade))
            report['cases'].append(record)
            (root / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
            (root / 'raw-responses.json').write_text(json.dumps(raw, indent=2, ensure_ascii=False))
            print(json.dumps({k: record.get(k) for k in ('name', 'strict_validation_passed', 'finding_matches_expected', 'assessment_seconds', 'grade_rows')}), flush=True)
    if not all(c.get('strict_validation_passed') for c in report['cases']): raise SystemExit(1)


if __name__ == '__main__': main()
