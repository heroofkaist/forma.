"""Synthetic contract and authenticated lifecycle regressions; no live model calls."""
import copy
import pytest
from sqlalchemy import select, func, inspect
from test_accounts_courses import platform, identity, create_course
from test_document_processing import setup_submission
import assessment_api
import document_processing
from assessment_models import AssessmentRubric, AssessmentSuggestion, AssessmentDecision
from services.assessment import validate_assessment, RubricSpec, STRATEGIES
from processing_models import DocumentInterpretation, ProcessingJob
from document_models import DocumentReview
from persistence import AcademicAssignment, AcademicGrade, AcademicSubmission
from migrations import apply_migrations


def suggestion(rubric, source, finding='concern'):
    section = next(s for s in source['sections'] if s['transcription'])
    return {'criteria': [{'question_id': c['question_id'], 'criterion_id': c['criterion_id'],
        'proposed_score': 1, 'rationale': 'Synthetic rationale', 'evidence': [{'section_id': section['id'], 'page_number': section['page_number'], 'quote': section['transcription'][:10]}],
        'interpretation': 'Synthetic interpretation, not an independently verified fact.', 'finding': finding,
        'suggested_improvement': 'Explain the reasoning.', 'missing_evidence': [], 'uncertainty': [], 'verification_status': 'needs_review'} for c in rubric['criteria']]}


@pytest.fixture
def assessed(platform, monkeypatch):
    values = setup_submission(platform, monkeypatch)
    client, factory, teacher, student, sid, structure, assignment, content = values
    monkeypatch.setattr(assessment_api, 'SessionLocal', factory)
    # Existing understanding slice produces immutable observed evidence first.
    assert client.post('/api/document-analysis/' + sid, headers=teacher, json={}).status_code == 202
    assert document_processing.process_one()
    path = '/api/assessment/' + sid
    rubric_path = '/api/assessment-rubrics/' + assignment['id']
    response = client.get(rubric_path, headers=teacher)
    assert response.status_code == 200, response.text
    candidate = response.json()['candidate']
    candidate['instructions'] = 'Calculate force and explain your method, showing equations and units.'
    for i, c in enumerate(candidate['criteria']):
        c['description'] = 'Explain reasoning for question ' + str(i + 1)
        c['insight_tag'] = 'reasoning' + str(i + 1)
    assert client.post(rubric_path, headers=teacher, json=candidate).status_code == 201
    import services.assessment as service
    monkeypatch.setattr(service, 'evaluate', lambda snap, *args, **kwargs: (suggestion(snap['rubric'], snap['source']), {'provider': 'ollama', 'ai_called': True}))
    return values, path, rubric_path, candidate


def test_one_contract_all_strategies_and_no_invented_evidence():
    source = {'sections': [{'id': 's1', 'page_number': 1, 'transcription': 'F = m / a = 2 N', 'readability': 'readable'}]}
    rubric = {'criteria': [{'question_id': 'q1', 'criterion_id': 'c1', 'maximum_points': 5}]}
    valid = suggestion(rubric, source)
    assert set(STRATEGIES) == {'problem_set', 'essay', 'lab_report', 'research_report', 'presentation', 'programming', 'general', 'homework'}
    assert validate_assessment(valid, rubric, source)['criteria'][0]['verification_status'] == 'needs_review'
    for mutation in [
        {'proposed_score': 6}, {'proposed_score': float('nan')}, {'verification_status': 'teacher_confirmed'},
        {'verification_status': 'independently_verified'}, {'criterion_id': 'invented'},
        {'evidence': [{'section_id': 's1', 'page_number': 2, 'quote': 'F'}]},
        {'evidence': [{'section_id': 'missing', 'page_number': 1, 'quote': 'F'}]},
        {'evidence': [{'section_id': 's1', 'page_number': 1, 'quote': 'invented'}]},
        {'evidence': []}, {'missing_evidence': ['Required computation absent']}
    ]:
        invalid = copy.deepcopy(valid); invalid['criteria'][0].update(mutation)
        with pytest.raises(ValueError): validate_assessment(invalid, rubric, source)
    invalid = copy.deepcopy(valid); invalid['criteria'] *= 2
    with pytest.raises(ValueError): validate_assessment(invalid, rubric, source)
    source['sections'][0]['readability'] = 'unreadable'
    with pytest.raises(ValueError): validate_assessment(valid, rubric, source)
    valid['criteria'][0].update(evidence=[], proposed_score=None, finding='insufficient_evidence')
    assert validate_assessment(valid, rubric, source)


def test_approval_local_snapshot_durable_draft_and_teacher_override(assessed, monkeypatch):
    values, path, rubric_path, spec = assessed
    client, factory, teacher, student, sid, *_ = values
    monkeypatch.setenv('FORMA_AI_PROVIDER', 'openrouter')
    monkeypatch.setenv('FORMA_AI_PAID_ENABLED', 'false')
    response = client.post(path, headers=teacher, json={})
    assert response.status_code == 202, response.text
    with factory() as db:
        job = db.get(ProcessingJob, response.json()['id'])
        assert job.context['ai']['name'] == 'ollama'
        assert job.context['assessment']['rubric']['instructions'] == spec['instructions']
        assert job.context['assessment']['title'] == 'Math work'
    assert document_processing.process_one()
    data = client.get(path, headers=teacher).json()
    draft = data['items'][0]
    assert len(draft['result']['criteria']) == 2
    assert all(c['verification_status'] == 'needs_review' for c in draft['result']['criteria'])
    assert client.get(path + '/insights', headers=teacher).json()['items'] == []
    decisions = [{'question_id': c['question_id'], 'criterion_id': c['criterion_id'], 'action': 'accepted', 'points': 4,
                  'feedback': 'Teacher corrected feedback', 'finding': 'concern'} for c in spec['criteria']]
    bad = copy.deepcopy(decisions); bad[0]['points'] = 6
    assert client.post(path + '/decisions', headers=teacher, json={'suggestion_id': draft['id'], 'decisions': bad}).status_code == 422
    response = client.post(path + '/decisions', headers=teacher, json={'suggestion_id': draft['id'], 'decisions': decisions})
    assert response.status_code == 201, response.text
    assert response.json()['review_id'] and response.json()['published'] is False
    with factory() as db:
        review = db.get(DocumentReview, response.json()['review_id'])
        assert review.criteria[0]['points'] == 4
        assert review.rubric_snapshot[0]['criteria'][0]['description'] == spec['criteria'][0]['description']
        assert db.scalar(select(func.count()).select_from(AcademicGrade)) == 0
        assert db.scalar(select(func.count()).select_from(AssessmentDecision)) == 1
        assert db.get(AssessmentSuggestion, draft['id']).result['criteria'][0]['proposed_score'] == 1
    assert client.get('/academic/student/grades', headers=student).json()['items'] == []
    insights = client.get(path + '/insights', headers=teacher).json()['items']
    assert insights[0]['confirmed_concerns'] == 1 and insights[0]['reviewed_submissions'] == 1
    # Rejection supersedes earlier confirmation, never erases it or publishes.
    for d in decisions: d.update(action='rejected', points=None)
    assert client.post(path + '/decisions', headers=teacher, json={'suggestion_id': draft['id'], 'decisions': decisions}).status_code == 201
    assert client.get(path + '/insights', headers=teacher).json()['items'] == []
    assert len(client.get(path, headers=teacher).json()['items'][0]['decisions']) == 2


def test_authorization_approval_and_format_boundaries(assessed):
    values, path, rubric_path, spec = assessed
    client, factory, teacher, student, sid, _, assignment, *_ = values
    for route in [path, path + '/insights', rubric_path]:
        assert client.get(route, headers=student).status_code == 403
    for route, body in [(path, {}), (rubric_path, spec), (rubric_path + '/draft', spec)]:
        assert client.post(route, headers=student, json=body).status_code == 403
    with factory() as db:
        submission = db.get(AcademicSubmission, sid); submission.file_type = 'pptx'; db.commit()
    assert client.post(path, headers=teacher, json={}).status_code == 202
    with factory() as db:
        db.get(AcademicSubmission, sid).file_type = 'pdf'
        approved = db.scalar(select(AssessmentRubric)); db.delete(approved); db.commit()
    assert client.post(path, headers=teacher, json={}).status_code == 409
    bad = copy.deepcopy(spec); bad['criteria'][0]['maximum_points'] = 999
    assert client.post(rubric_path, headers=teacher, json=bad).status_code == 422
    for category in ['presentation', 'research_report', 'programming']:
        bad = copy.deepcopy(spec); bad['category'] = category
        assert client.post(rubric_path, headers=teacher, json=bad).status_code == 422


def test_institution_isolation_and_no_paid_rubric_draft(platform, monkeypatch):
    values = setup_submission(platform, monkeypatch)
    client, factory, teacher, _, sid, _, assignment, *_ = values
    monkeypatch.setattr(assessment_api, 'SessionLocal', factory)
    outsider = identity(client, platform[2], 'outside@example.com')
    for route in ['/api/assessment/' + sid, '/api/assessment/' + sid + '/insights', '/api/assessment-rubrics/' + assignment['id']]:
        assert client.get(route, headers=outsider).status_code == 403


def test_additive_migration_and_paused_partial_source(assessed):
    values, path, _, _ = assessed
    client, factory, teacher, _, sid, *_ = values
    engine = factory.kw['bind']
    apply_migrations(engine); apply_migrations(engine)
    assert {'assessment_rubrics', 'assessment_suggestions', 'assessment_decisions'} <= set(inspect(engine).get_table_names())
    with factory() as db:
        source = db.scalar(select(DocumentInterpretation))
        db.get(ProcessingJob, source.job_id).usage = {'partial': True}
        db.commit()
    assert client.post(path, headers=teacher, json={}).status_code == 409


def test_unsafe_or_oversized_local_context_never_dispatches(monkeypatch):
    from services.ai_providers.engine import configuration
    from services.ai_providers.ollama import structured_completion
    import httpx
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: pytest.fail('Must fail before HTTP'))
    with pytest.raises(ValueError): structured_completion(configuration('ollama'), {}, '', {'text': 'x' * 19000})
    with pytest.raises(ValueError): structured_completion(configuration('gemini'), {}, '', {})

@pytest.mark.parametrize('category', ['problem_set', 'essay', 'lab_report'])
def test_real_core_contract_over_mocked_local_completion(platform, monkeypatch, category):
    import json
    from services.ai_providers import ollama
    values = setup_submission(platform, monkeypatch)
    client, factory, teacher, _, sid, _, assignment, *_ = values
    monkeypatch.setattr(assessment_api, 'SessionLocal', factory)
    with factory() as db:
        db.get(AcademicAssignment, assignment['id']).assignment_type = category; db.commit()
    assert client.post('/api/document-analysis/' + sid, headers=teacher, json={}).status_code == 202
    document_processing.process_one()
    rubric_path = '/api/assessment-rubrics/' + assignment['id']
    spec = client.get(rubric_path, headers=teacher).json()['candidate']
    spec['instructions'] = 'Use the submitted evidence to explain your reasoning in full.'
    for c in spec['criteria']: c['description'] = 'Explain the reasoning clearly.'
    assert client.post(rubric_path, headers=teacher, json=spec).status_code == 201
    observed = []
    def local(config, schema, system, context, progress=None, observe=None):
        observed.append(context)
        assert config.name == 'ollama' and config.model == 'qwen3-vl:8b-instruct'
        if progress: progress()
        return {'message': {'content': json.dumps(suggestion(context['rubric'], context['source']))}, 'done': True}
    monkeypatch.setattr(ollama, 'structured_completion', local)
    path = '/api/assessment/' + sid
    assert client.post(path, headers=teacher, json={}).status_code == 202
    document_processing.process_one()
    assert client.get(path, headers=teacher).json()['items'][0]['result']['criteria']
    assert observed[0]['rubric']['category'] == category
    assert observed[0]['source_limitations']['external_facts_verified'] is False
    assert observed[0]['source_limitations']['code_executed'] is False


def test_rubric_draft_requires_explicit_approval_and_failed_output_not_saved(assessed, monkeypatch):
    import json
    from services.ai_providers import ollama
    values, path, rubric_path, spec = assessed
    client, factory, teacher, *_ = values
    def local(config, schema, system, context, *args):
        assert config.name == 'ollama'
        return {'message': {'content': json.dumps(context)}}
    monkeypatch.setattr(ollama, 'structured_completion', local)
    with factory() as db: before = db.scalar(select(func.count()).select_from(AssessmentRubric))
    response = client.post(rubric_path + '/draft', headers=teacher, json=spec)
    assert response.status_code == 200 and response.json()['approved'] is False
    with factory() as db: assert db.scalar(select(func.count()).select_from(AssessmentRubric)) == before
    def corrupt(*args): return {'message': {'content': '{"not_a_rubric": true}'}}
    monkeypatch.setattr(ollama, 'structured_completion', corrupt)
    assert client.post(rubric_path + '/draft', headers=teacher, json=spec).status_code == 422


def test_additional_categories_have_explicit_static_reasoning_limits():
    from scripts.assessment_fixtures import FUTURE_CASES
    assert {c['category'] for c in FUTURE_CASES}.issubset(STRATEGIES)
    assert 'never executed' in STRATEGIES['programming'].guidance
    assert 'speaking' in STRATEGIES['presentation'].guidance
    assert any('FAILED' in c['text'] for c in FUTURE_CASES)


def test_assessment_failure_retains_source_and_previous_versions(assessed, monkeypatch):
    values, path, *_ = assessed
    client, factory, teacher, _, sid, *_ = values
    import services.assessment as service
    def invalid(*args, **kwargs): raise ValueError('invalid synthetic output')
    monkeypatch.setattr(service, 'evaluate', invalid)
    response = client.post(path, headers=teacher, json={}); assert response.status_code == 202
    document_processing.process_one()
    with factory() as db:
        assert db.get(ProcessingJob, response.json()['id']).status == 'failed'
        assert db.scalar(select(func.count()).select_from(DocumentInterpretation)) == 1
        assert db.scalar(select(func.count()).select_from(AssessmentSuggestion)) == 0
        assert db.get(AcademicSubmission, sid).file_path == 'synthetic.pdf'


def test_pdf_line_wrap_grounding_persists_exact_unique_source_span():
    source = {'sections': [{'id': 's1', 'page_number': 1, 'transcription': 'A pilot would limit\nthat cost.', 'readability': 'readable'}]}
    rubric = {'criteria': [{'question_id': 'q1', 'criterion_id': 'c1', 'maximum_points': 5}]}
    value = suggestion(rubric, source)
    value['criteria'][0]['evidence'][0]['quote'] = 'A pilot would limit that cost.'
    result = validate_assessment(value, rubric, source)
    assert result['criteria'][0]['evidence'][0]['quote'] == source['sections'][0]['transcription']
    value['criteria'][0]['evidence'][0]['quote'] = 'A pilot will limit that cost.'
    with pytest.raises(ValueError): validate_assessment(value, rubric, source)


def test_local_reasoning_transport_is_loopback_bounded_and_unloads(monkeypatch):
    import httpx
    from services.ai_providers.engine import configuration
    from services.ai_providers.ollama import structured_completion
    real = httpx.Client; calls = []
    def handler(request):
        import json
        calls.append(request.url.path)
        assert request.url.host == '127.0.0.1' and request.headers.get('authorization') is None
        if request.url.path == '/api/ps': return httpx.Response(200, json={'models': []})
        payload = json.loads(request.content)
        assert payload['model'] == 'qwen3-vl:8b-instruct'
        if request.url.path == '/api/show': return httpx.Response(200, json={'capabilities': ['vision']})
        if request.url.path == '/api/chat':
            assert payload['options']['num_ctx'] == 8192 and payload['stream'] is False
            assert payload['options']['num_predict'] <= 4096
            return httpx.Response(200, json={'done': True, 'message': {'content': '{}'}})
        assert request.url.path == '/api/generate' and payload['keep_alive'] == 0
        return httpx.Response(200, json={})
    def client(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        return real(**kwargs, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, 'Client', client)
    assert structured_completion(configuration('ollama'), {}, 'No tools.', {})['done']
    assert calls == ['/api/ps', '/api/show', '/api/chat', '/api/generate']


def test_migration_009_upgrades_old_schema_without_rewriting_sources(assessed):
    values, *_ = assessed
    client, factory, teacher, _, sid, *_ = values
    from account_models import SchemaMigration
    engine = factory.kw['bind']
    apply_migrations(engine)
    with engine.begin() as connection:
        for cls in (AssessmentDecision, AssessmentSuggestion, AssessmentRubric): cls.__table__.drop(connection)
        connection.execute(SchemaMigration.__table__.delete().where(SchemaMigration.version == '009_rubric_assessment'))
    apply_migrations(engine); apply_migrations(engine)
    with factory() as db:
        assert db.get(AcademicSubmission, sid).file_name == 'synthetic.pdf'
        assert db.scalar(select(func.count()).select_from(DocumentInterpretation)) == 1
        assert db.scalar(select(func.count()).select_from(SchemaMigration)) == 15


def test_single_click_durable_read_then_grade_deduplicates_and_never_publishes(platform, monkeypatch):
    values = setup_submission(platform, monkeypatch)
    client, factory, teacher, student, sid, structure, assignment, content = values
    monkeypatch.setattr(assessment_api, 'SessionLocal', factory)
    with factory() as db:
        row = db.get(AcademicAssignment, assignment['id'])
        row.description = 'Solve each question and show your method.'
        row.questions = [{**q, 'criteria': [{**c, 'description': 'Show the physical reasoning and calculations'} for c in q['criteria']]} for q in row.questions]
        db.commit()
    import services.assessment as service
    monkeypatch.setattr(service, 'evaluate', lambda snap, *args, **kwargs: (suggestion(snap['rubric'], snap['source']), {'ai_called': True}))
    path = '/api/assessment/' + sid
    assert client.post(path, headers=student, json={'prepare': True}).status_code == 403
    first = client.post(path, headers=teacher, json={'prepare': True})
    assert first.status_code == 202, first.text
    assert first.json()['status'] == 'awaiting_source'
    assert client.post(path, headers=teacher, json={'prepare': True}).json()['id'] == first.json()['id']
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ProcessingJob)) == 2
        assert db.scalar(select(func.count()).select_from(AssessmentSuggestion)) == 0
    assert document_processing.process_one()  # reading only
    assert client.get(path, headers=teacher).json()['items'] == []
    assert document_processing.process_one()  # worker activates durable dependency, then grades
    body = client.get(path, headers=teacher).json()
    assert len(body['items']) == 1
    assert body['items'][0]['job_id'] == first.json()['id']
    assert [c['proposed_score'] for c in body['items'][0]['result']['criteria']] == [1, 1]
    # A lost response retried after completion still reuses the original pipeline.
    assert client.post(path, headers=teacher, json={'prepare': True}).json()['id'] == first.json()['id']
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ProcessingJob)) == 2
        assert db.scalar(select(func.count()).select_from(DocumentInterpretation)) == 1
        assert db.scalar(select(func.count()).select_from(AcademicGrade)) == 0
        assert db.scalar(select(func.count()).select_from(AssessmentDecision)) == 0


@pytest.mark.parametrize('failure', ['partial', 'failed'])
def test_pipeline_refuses_partial_read_and_failed_parent(platform, monkeypatch, failure):
    values = setup_submission(platform, monkeypatch)
    client, factory, teacher, student, sid, structure, assignment, content = values
    monkeypatch.setattr(assessment_api, 'SessionLocal', factory)
    with factory() as db:
        row = db.get(AcademicAssignment, assignment['id'])
        row.description = 'Solve each question and show your method.'
        row.questions = [{**q, 'criteria': [{**c, 'description': 'Show the physical reasoning and calculations'} for c in q['criteria']]} for q in row.questions]
        db.commit()
    response = client.post('/api/assessment/' + sid, headers=teacher, json={'prepare': True})
    assert response.status_code == 202, response.text
    assert document_processing.process_one()
    from services.assessment_pipeline import activate_waiting
    with factory() as db:
        child = db.get(ProcessingJob, response.json()['id'])
        parent = db.get(ProcessingJob, child.context['depends_on'])
        if failure == 'partial': parent.usage = {**parent.usage, 'partial': True}
        else: parent.status = 'failed'
        db.commit()
        activate_waiting(db); db.commit()
        assert child.status == 'failed'
        assert ('Partial document coverage' in child.error) if failure == 'partial' else ('Распознавание не завершено' in child.error)
        assert db.scalar(select(func.count()).select_from(AssessmentSuggestion)) == 0


def test_pipeline_exposes_paused_reading_and_resumes_only_with_available_budget(platform, monkeypatch):
    client, factory, teacher, student, sid, structure, assignment, content = setup_submission(platform, monkeypatch)
    monkeypatch.setattr(assessment_api, 'SessionLocal', factory)
    with factory() as db:
        row = db.get(AcademicAssignment, assignment['id'])
        row.description = 'Solve and explain your physical reasoning.'
        row.questions = [{**q, 'criteria': [{**c, 'description': 'Explain the method and show calculations'} for c in q['criteria']]} for q in row.questions]
        db.commit()
    path = '/api/assessment/' + sid
    response = client.post(path, headers=teacher, json={'prepare': True})
    assert response.status_code == 202, response.text
    with factory() as db:
        child = db.get(ProcessingJob, response.json()['id'])
        parent = db.get(ProcessingJob, child.context['depends_on'])
        parent.context = {**parent.context, 'ai': {**parent.context['ai'], 'name': 'openrouter'}}
        parent.status = 'awaiting_budget'; parent.attempts = 1; parent.error = 'Allowance paused.'; db.commit()
    assert client.get(path, headers=teacher).json()['jobs'][0]['status'] == 'awaiting_budget'
    monkeypatch.setattr('ai_budget.can_resume', lambda *args, **kwargs: False)
    assert client.post(path + '/resume', headers=student).status_code == 403
    assert client.post(path + '/resume', headers=teacher).status_code == 409
    monkeypatch.setattr('ai_budget.can_resume', lambda *args, **kwargs: True)
    resumed = client.post(path + '/resume', headers=teacher)
    assert resumed.status_code == 202 and resumed.json()['id'] == response.json()['id']
    with factory() as db:
        assert db.get(ProcessingJob, child.id).status == 'awaiting_source'
        assert db.get(ProcessingJob, parent.id).status == 'queued'
        assert db.scalar(select(func.count()).select_from(AssessmentSuggestion)) == 0
        assert db.scalar(select(func.count()).select_from(AcademicGrade)) == 0


@pytest.mark.parametrize('contradiction', ['missing_evidence', 'insufficient_finding', 'no_quote'])
def test_conflicting_score_is_withheld_without_losing_other_criteria_or_calling_again(monkeypatch, contradiction):
    import json
    from services.assessment import evaluate, reconcile_score_evidence
    from services.ai_providers.engine import configuration
    rubric = {'category': 'lab_report', 'instructions': 'Solve the four numbered tasks.', 'reference_material': '',
        'criteria': [{'question_id': 'q1', 'criterion_id': f'c{i}', 'description': f'{i} задача', 'maximum_points': 25} for i in range(1, 5)]}
    source = {'sections': [{'id': 'p1-s1', 'page_number': 1, 'question_id': 'q1',
        'transcription': 'Problem 1: F = ma. Problem 2: W = Fd. Problem 3: P = W/t.', 'readability': 'readable'}]}
    raw = suggestion(rubric, source)
    raw['criteria'][0]['proposed_score'] = 0  # A supported real zero stays zero.
    raw['criteria'][1]['proposed_score'] = 21
    bad = raw['criteria'][3]
    bad['proposed_score'] = 0  # Production trigger: zero with unavailable source, not an observed wrong solution.
    if contradiction == 'missing_evidence': bad['missing_evidence'] = ['Ответ на задачу 4 не найден.']
    elif contradiction == 'insufficient_finding': bad['finding'] = 'insufficient_evidence'
    else: bad['evidence'] = []
    before = copy.deepcopy(raw)
    with pytest.raises(ValueError): validate_assessment(raw, rubric, source)
    calls = []
    def complete(*args, **kwargs):
        calls.append(True)
        return {'done': True, 'done_reason': 'stop', 'message': {'content': json.dumps(raw)}}
    monkeypatch.setattr('services.ai_providers.ollama.structured_completion', complete)
    snapshot = {'rubric': rubric, 'title': 'Midterm', 'source': source, 'source_limitations': {}}
    checkpoints = []
    first, usage = evaluate(snapshot, configuration('ollama'), checkpoint=lambda chunks: checkpoints.extend(copy.deepcopy(chunks[len(checkpoints):])))
    assert [c['proposed_score'] for c in first['criteria']] == [0, 21, 1, None]
    assert first['criteria'][3]['finding'] == 'insufficient_evidence'
    assert first['criteria'][3]['uncertainty'][0].startswith('Балл модели снят:')
    assert usage['validation_notes'] == [{'question_id': 'q1', 'criterion_id': 'c4', 'code': 'score_withheld_insufficient_evidence'}]
    again, resumed_usage = evaluate(snapshot, configuration('ollama'), checkpoints=checkpoints)
    assert again == first and len(calls) == 1 and resumed_usage['validation_notes'] == usage['validation_notes']
    assert raw == before  # Never mutate the source response in place.
    assert reconcile_score_evidence(first) == (first, [])


def test_score_reconciliation_does_not_approve_invented_evidence_or_identifiers():
    from services.assessment import reconcile_score_evidence
    from services.assessment_errors import AssessmentValidationError
    rubric = {'criteria': [{'question_id': 'q1', 'criterion_id': 'c1', 'maximum_points': 5}]}
    source = {'sections': [{'id': 's1', 'page_number': 1, 'transcription': 'F = ma.', 'readability': 'readable'}]}
    for patch, reason in [({'evidence': [{'section_id': 's1', 'page_number': 1, 'quote': 'invented proof'}]}, 'assessment_evidence_quote'),
                          ({'criterion_id': 'invented'}, 'assessment_criteria_mismatch'), ({'proposed_score': 6}, 'assessment_score_out_of_range')]:
        raw = suggestion(rubric, source); raw['criteria'][0].update(patch)
        normalized, notes = reconcile_score_evidence(raw)
        assert not notes
        with pytest.raises(AssessmentValidationError) as error: validate_assessment(normalized, rubric, source)
        assert error.value.reason == reason
