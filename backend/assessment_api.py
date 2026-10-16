"""Authorized rubric approval, configured assessment drafts and explicit teacher decisions."""
import json
import httpx
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import Field
from sqlalchemy import select
from accounts import utc, rate_limit
from auth import request_user
from permissions import require_teacher
from institutions import audit
from persistence import SessionLocal, AcademicAssignment, AcademicSubmission, CourseOffering
from processing_models import DocumentInterpretation, ProcessingJob
from document_models import DocumentReview
from document_review import get_submission
from assessment_models import AssessmentRubric, AssessmentSuggestion, AssessmentDecision
from services.assessment import Strict, RubricSpec, rubric_for_assignment, STRATEGIES
from review_pilot_contracts import CardUse
from services.ai_providers.engine import configuration
from document_processing import enqueue

router = APIRouter(prefix='/api', tags=['Rubric assessment'])


def assignment_access(db, identifier, request):
    assignment = db.get(AcademicAssignment, identifier)
    if not assignment: raise HTTPException(404, 'Assignment not found.')
    require_teacher(db, request_user(request), assignment.offering_id)
    return assignment


def latest_rubric(db, aid):
    return db.scalar(select(AssessmentRubric).where(AssessmentRubric.assignment_id == aid).order_by(AssessmentRubric.created_at.desc(), AssessmentRubric.id.desc()).limit(1))


def default_spec(assignment):
    instructions = assignment.description + '\n' + '\n'.join(q['title'] + ': ' + q.get('statement', '') for q in assignment.questions)
    return {'category': assignment.assignment_type, 'instructions': instructions,
        'reference_material': '\n'.join(q.get('reference_solution', '') for q in assignment.questions),
        'criteria': [{'question_id': q['id'], 'criterion_id': c['criterion_id'], 'description': c['description'],
            'maximum_points': c['maximum_points'], 'performance_descriptions': c.get('partial_credit', ''),
            'feedback_requirements': c.get('evidence_expected', ''), 'weight': None, 'insight_tag': ''}
            for q in assignment.questions for c in q['criteria']]}


def rubric_json(row):
    return {'id': row.id, 'spec': row.spec, 'approved_by': row.approved_by, 'created_at': utc(row.created_at)} if row else None


@router.get('/assessment-rubrics/{assignment_id}')
def rubric(assignment_id: str, request: Request):
    with SessionLocal() as db:
        assignment = assignment_access(db, assignment_id, request)
        return {'approved': rubric_json(latest_rubric(db, assignment_id)), 'candidate': default_spec(assignment),
                'supported': assignment.assignment_type in STRATEGIES, 'title': assignment.title}


@router.post('/assessment-rubrics/{assignment_id}', status_code=201)
def approve(assignment_id: str, payload: RubricSpec, request: Request):
    with SessionLocal() as db:
        assignment = assignment_access(db, assignment_id, request)
        try: spec = rubric_for_assignment(payload, assignment)
        except ValueError as error: raise HTTPException(422, str(error)) from error
        user = request_user(request)
        rate_limit(request, 'rubric-approve', user.account_id or user.username, 20)
        row = AssessmentRubric(assignment_id=assignment_id, spec=spec, approved_by=user.username)
        db.add(row); db.flush()
        audit(db, user, 'assessment.rubric.approve', row.id, {'assignment_id': assignment_id})
        db.commit(); return rubric_json(row)


@router.post('/assessment-rubrics/{assignment_id}/draft')
def draft_rubric(assignment_id: str, payload: RubricSpec, request: Request):
    # Explicit optional local inference; never automatically approves the result.
    with SessionLocal() as db:
        assignment = assignment_access(db, assignment_id, request)
        try: spec = rubric_for_assignment(payload, assignment)
        except ValueError as error: raise HTTPException(422, str(error)) from error
        rate_limit(request, 'rubric-draft', request_user(request).account_id or request_user(request).username, 3)
    from services.ai_providers.ollama import structured_completion
    from services.assessment import SYSTEM
    try:
        config = configuration('ollama')
        # Keep the optional synchronous draft within the existing BFF timeout.
        config.options['timeout'] = min(config.options['timeout'], 45)
        data = structured_completion(config, RubricSpec.model_json_schema(), SYSTEM +
            '\nDraft clearer rubric performance descriptions and feedback requirements. Preserve all criterion IDs, category, instructions, reference_material, weights, insight tags and maximum_points. No scores. Teacher approval is required.', spec)
        candidate = rubric_for_assignment(json.loads(data['message']['content']), assignment)
        # Draft generation may clarify prose but cannot rewrite the task or weights.
        if any(candidate[k] != spec[k] for k in ('category', 'instructions', 'reference_material')):
            raise ValueError('Draft changed assignment requirements.')
        for before, after in zip(spec['criteria'], candidate['criteria']):
            if any(before[k] != after[k] for k in ('question_id', 'criterion_id', 'weight', 'insight_tag', 'maximum_points')):
                raise ValueError('Draft changed rubric identity or weights.')
    except (ValueError, KeyError) as error:
        raise HTTPException(422, 'Local rubric draft failed validation. Refine the rubric manually.') from error
    except (httpx.HTTPError, TimeoutError) as error:
        raise HTTPException(503, 'The local model is unavailable or busy. Refine the rubric manually or retry later.') from error
    return {'candidate': candidate, 'approved': False, 'provider': 'ollama'}


@router.get('/assessment/{submission_id}')
def assessment(submission_id: str, request: Request):
    with SessionLocal() as db:
        _, assignment = get_submission(db, submission_id, request, teacher=True)
        rows = db.scalars(select(AssessmentSuggestion).where(AssessmentSuggestion.submission_id == submission_id).order_by(AssessmentSuggestion.created_at.desc())).all()
        items = []
        for row in rows:
            reviews = db.scalars(select(AssessmentDecision).where(AssessmentDecision.suggestion_id == row.id).order_by(AssessmentDecision.created_at.desc())).all()
            items.append({'id': row.id, 'job_id': row.job_id, 'result': row.result,
                'rubric': rubric_json(db.get(AssessmentRubric, row.rubric_id)), 'interpretation_id': row.interpretation_id,
                'correction_id': row.correction_id, 'source': db.get(ProcessingJob, row.job_id).context['assessment']['source'],
                'decisions': [{'id': r.id, 'reviewer': r.reviewer, 'decisions': r.decisions, 'review_id': r.review_id, 'created_at': utc(r.created_at)} for r in reviews]})
        jobs = db.scalars(select(ProcessingJob).where(ProcessingJob.submission_id == submission_id).order_by(ProcessingJob.created_at.desc())).all()
        from services.assessment_pipeline import job_state
        return {'items': items, 'jobs': [job_state(db, j) for j in jobs if j.context.get('task') == 'assessment'],
            'supported': assignment.assignment_type in STRATEGIES}


class AssessRequest(Strict):
    reanalyze: bool = False
    prepare: bool = False
    base_suggestion_id: str | None = Field(default=None, max_length=36)
    target_criteria: list[tuple[str, str]] = Field(default_factory=list, max_length=1)


@router.post('/assessment/{submission_id}', status_code=202)
def request_assessment(submission_id: str, payload: AssessRequest, request: Request):
    with SessionLocal() as db:
        submission, assignment = get_submission(db, submission_id, request, teacher=True)
        user = request_user(request)
        if bool(payload.base_suggestion_id) != bool(payload.target_criteria):
            raise HTTPException(422, 'Choose a saved assessment and one criterion to recheck.')
        rate_limit(request, 'assessment', user.account_id or user.username, 10)
        # Serialize approval + both enqueue stages together, including first-click races.
        from sqlalchemy import text, update
        if db.bind.dialect.name == 'postgresql': db.execute(text('SELECT pg_advisory_xact_lock(62401704)'))
        else: db.execute(update(ProcessingJob).where(ProcessingJob.status == 'queued').values(stage=ProcessingJob.stage))
        approved = latest_rubric(db, assignment.id)
        if not approved:
            # Requesting assessment confirms the criteria already supplied by this teacher.
            try: spec = rubric_for_assignment(default_spec(assignment), assignment)
            except ValueError as error: raise HTTPException(409, str(error)) from error
            approved = AssessmentRubric(assignment_id=assignment.id, spec=spec, approved_by=request_user(request).username)
            db.add(approved); db.flush()
        try: rubric_for_assignment(approved.spec, assignment)
        except ValueError as error: raise HTTPException(409, 'The approved rubric no longer matches the assignment.') from error
        pending = db.scalars(select(ProcessingJob).where(ProcessingJob.submission_id == submission_id,
            ProcessingJob.status.in_(['awaiting_source', 'queued', 'extracting', 'interpreting']))).all()
        existing = next((j for j in pending if j.context.get('task') == 'assessment'), None)
        if existing: return {'id': existing.id, 'status': existing.status}
        source = db.scalar(select(DocumentInterpretation).where(DocumentInterpretation.submission_id == submission_id).order_by(DocumentInterpretation.created_at.desc()).limit(1))
        if payload.target_criteria and not source: raise HTTPException(409, 'Saved assessment cannot be reused. Reassess the whole work.')
        if not source and not payload.prepare: raise HTTPException(409, 'Run document understanding and review its observations first.')
        from services.ai_providers.engine import assessment_configuration
        try: config = assessment_configuration()
        except ValueError as error: raise HTTPException(409, str(error)) from error
        from services.assessment_pipeline import snapshot
        if source:
            try: context = {'task': 'assessment', 'assessment': snapshot(db, submission, assignment, approved, source)}
            except ValueError as error: raise HTTPException(409, str(error)) from error
            if payload.target_criteria:
                baseline = db.get(AssessmentSuggestion, payload.base_suggestion_id)
                if not baseline or baseline.submission_id != submission_id:
                    raise HTTPException(404, 'Saved assessment not found.')
                prior = db.get(ProcessingJob, baseline.job_id)
                previous_snapshot = {k: v for k, v in prior.context.get('assessment', {}).items()
                    if k not in {'target_criteria', 'reuse_criteria', 'base_suggestion_id'}}
                if previous_snapshot != context['assessment']:
                    raise HTTPException(409, 'Requirements, teaching guide or source changed. Reassess the whole work.')
                keys = {(c['question_id'], c['criterion_id']) for c in approved.spec['criteria']}
                selected = set(payload.target_criteria)
                if not selected <= keys: raise HTTPException(422, 'Choose a current criterion.')
                from services.assessment import validate_assessment
                try: saved_result = validate_assessment(baseline.result, approved.spec, context['assessment']['source'], context['assessment']['assignment_context'].get('answer_groups', []))
                except ValueError as error: raise HTTPException(409, 'Saved assessment cannot be reused. Reassess the whole work.') from error
                context['assessment'].update(target_criteria=[list(key) for key in payload.target_criteria], base_suggestion_id=baseline.id,
                    reuse_criteria=[c for c in saved_result['criteria'] if (c['question_id'], c['criterion_id']) not in selected])
            if not payload.reanalyze:
                from dataclasses import asdict
                previous = db.scalars(select(AssessmentSuggestion).where(AssessmentSuggestion.submission_id == submission_id,
                    AssessmentSuggestion.interpretation_id == source.id, AssessmentSuggestion.rubric_id == approved.id)).all()
                for saved in previous:
                    prior = db.get(ProcessingJob, saved.job_id)
                    if prior.context.get('assessment') == context['assessment'] and prior.context.get('ai') == asdict(config):
                        return {'id': prior.id, 'status': prior.status}
        try:
            if not source:
                reading = enqueue(db, submission, assignment, user.account_id or user.username)
                if reading.status == 'failed':
                    reading = enqueue(db, submission, assignment, user.account_id or user.username, force=True)
                context = {'task': 'assessment', 'depends_on': reading.id, 'rubric_id': approved.id}
            job = enqueue(db, submission, assignment, user.account_id or user.username, payload.reanalyze,
                          task_context=context, provider_config=config)
            if job.status == 'failed' and not payload.reanalyze:
                job = enqueue(db, submission, assignment, user.account_id or user.username, True,
                              task_context=context, provider_config=config)
        except ValueError as error: raise HTTPException(429, str(error)) from error
        audit(db, user, 'assessment.request', job.id, {'submission_id': submission_id, 'rubric_id': approved.id})
        db.commit(); return {'id': job.id, 'status': job.status}


@router.post('/assessment/{submission_id}/resume', status_code=202)
def resume_assessment(submission_id: str, request: Request):
    import ai_budget
    from persistence import now_utc
    from document_processing import ACTIVE, MAX_ATTEMPTS
    from sqlalchemy import text, update
    with SessionLocal() as db:
        get_submission(db, submission_id, request, teacher=True)
        user = request_user(request)
        rate_limit(request, 'assessment-resume', user.account_id or user.username, 10)
        if db.bind.dialect.name == 'postgresql': db.execute(text('SELECT pg_advisory_xact_lock(62401704)'))
        else: db.execute(update(ProcessingJob).where(ProcessingJob.submission_id == submission_id).values(stage=ProcessingJob.stage))
        jobs = db.scalars(select(ProcessingJob).where(ProcessingJob.submission_id == submission_id).order_by(ProcessingJob.created_at.desc())).all()
        child = next((j for j in jobs if j.context.get('task') == 'assessment'), None)
        job = db.get(ProcessingJob, child.context['depends_on']) if child and child.status == 'awaiting_source' else child
        if (not job or job.status != 'awaiting_budget' or job.attempts >= MAX_ATTEMPTS or
            job.context.get('ai', {}).get('name') != 'openrouter' or not ai_budget.can_resume(job.id, db=db)):
            raise HTTPException(409, 'Paid allowance is not available; reconcile billing or use manual review.')
        if any(j.status in ('queued', *ACTIVE) for j in jobs):
            raise HTTPException(409, 'Another document task is active; wait for it to finish.')
        job.status = job.stage = 'queued'; job.available_at = now_utc()
        audit(db, user, 'assessment.resume', job.id, {'submission_id': submission_id})
        db.commit()
        return {'id': child.id, 'status': 'awaiting_source' if child.id != job.id else 'queued'}


class Decision(Strict):
    question_id: str = Field(max_length=80)
    criterion_id: str = Field(max_length=80)
    action: Literal['accepted', 'rejected', 'deferred']
    points: float | None = Field(ge=0, le=10000, allow_inf_nan=False)
    feedback: str = Field(max_length=4000)
    finding: Literal['strength', 'concern', 'mixed', 'insufficient_evidence']
    card_use: CardUse | None = None


class Decisions(Strict):
    suggestion_id: str = Field(max_length=36)
    decisions: list[Decision] = Field(min_length=1, max_length=12)
    draft: bool = False
    feedback: str | None = Field(default=None, max_length=10000)


@router.post('/assessment/{submission_id}/decisions', status_code=201)
def confirm(submission_id: str, payload: Decisions, request: Request):
    with SessionLocal() as db:
        submission, assignment = get_submission(db, submission_id, request, teacher=True)
        row = db.get(AssessmentSuggestion, payload.suggestion_id)
        if not row or row.submission_id != submission_id: raise HTTPException(404, 'Assessment not found.')
        rubric = db.get(AssessmentRubric, row.rubric_id)
        try: rubric_for_assignment(rubric.spec, assignment)
        except ValueError as error: raise HTTPException(409, 'Rubric changed; manually review using the current assignment.') from error
        criteria = {(c['question_id'], c['criterion_id']): c for c in rubric.spec['criteria']}
        identifiers = [(d.question_id, d.criterion_id) for d in payload.decisions]
        if len(set(identifiers)) != len(identifiers) or set(identifiers) != set(criteria):
            raise HTTPException(422, 'Review every criterion exactly once.')
        for d in payload.decisions:
            if d.points is not None and d.points > criteria[(d.question_id, d.criterion_id)]['maximum_points']:
                raise HTTPException(422, 'Teacher score exceeds criterion maximum.')
            if d.action != 'accepted' and d.points is not None:
                raise HTTPException(422, 'Only explicitly accepted teacher decisions can carry points.')
        user = request_user(request)
        from review_pilot import validate_use, questions_for_spec
        approved_questions = questions_for_spec(assignment, rubric.spec)
        for d in payload.decisions:
            validate_use(db, submission, assignment, d.question_id, d.criterion_id, d.card_use, approved_questions)
        saved_decisions = [dict(d.model_dump(), confirmed=not payload.draft) for d in payload.decisions]
        if payload.feedback is not None: saved_decisions[0]['overall_feedback'] = payload.feedback
        record = AssessmentDecision(suggestion_id=row.id, reviewer=user.username, decisions=saved_decisions)
        # Reuse existing unpublished manual reviews; publication remains separate.
        if not payload.draft and all(d.action == 'accepted' and d.points is not None for d in payload.decisions):
            review = DocumentReview(submission_id=submission_id, reviewer=user.username,
                criteria=[{'question_id': d.question_id, 'criterion_id': d.criterion_id, 'points': d.points, 'comment': d.feedback, 'card_use': d.card_use.model_dump() if d.card_use else None} for d in payload.decisions],
                rubric_snapshot=approved_questions, feedback=payload.feedback if payload.feedback is not None else '\n\n'.join(d.feedback for d in payload.decisions))
            db.add(review); db.flush(); record.review_id = review.id
        db.add(record); db.flush()
        job = db.get(ProcessingJob, row.job_id)
        job.status = 'needs_review' if payload.draft or any(d.action == 'deferred' for d in payload.decisions) else 'completed'
        job.stage = 'review' if job.status == 'needs_review' else 'completed'
        audit(db, user, 'assessment.teacher.draft' if payload.draft else 'assessment.teacher.decide', record.id, {'suggestion_id': row.id, 'draft': payload.draft})
        db.commit(); return {'id': record.id, 'review_id': record.review_id, 'published': False}


@router.get('/assessment/{submission_id}/insights')
def insights(submission_id: str, request: Request):
    with SessionLocal() as db:
        student, assignment = get_submission(db, submission_id, request, teacher=True)
        course_id = db.get(CourseOffering, assignment.offering_id).course_id
        # Only same-student submissions in this course, with independent access checks.
        submissions = db.scalars(select(AcademicSubmission).join(AcademicAssignment).join(CourseOffering).where(
            AcademicSubmission.student_id == student.student_id, CourseOffering.course_id == course_id)).all()
        seen = set(); groups = {}
        for submission in submissions:
            other = db.get(AcademicAssignment, submission.assignment_id)
            require_teacher(db, request_user(request), other.offering_id)
            reviews = db.execute(select(AssessmentDecision, AssessmentSuggestion, AssessmentRubric).join(
                AssessmentSuggestion, AssessmentDecision.suggestion_id == AssessmentSuggestion.id).join(
                AssessmentRubric, AssessmentSuggestion.rubric_id == AssessmentRubric.id).where(
                AssessmentSuggestion.submission_id == submission.id).order_by(AssessmentDecision.created_at.desc())).all()
            for review, suggestion, rubric in reviews:
                lookup = {(c['question_id'], c['criterion_id']): c for c in rubric.spec['criteria']}
                for d in review.decisions:
                    if d.get('confirmed') is False: continue  # Drafts do not replace authoritative decisions.
                    c = lookup[(d['question_id'], d['criterion_id'])]; tag = c.get('insight_tag')
                    key = (submission.id, rubric.spec['category'], tag)
                    if not tag or key in seen: continue
                    seen.add(key)  # A later rejection/defer supersedes earlier acceptance.
                    if d['action'] != 'accepted': continue
                    label = (rubric.spec['category'], tag)
                    group = groups.setdefault(label, {'category': label[0], 'tag': tag, 'confirmed_concerns': 0, 'reviewed_submissions': 0, 'evidence': []})
                    group['reviewed_submissions'] += 1
                    if d['finding'] in {'concern', 'mixed'}:
                        group['confirmed_concerns'] += 1
                        finding = next(c for c in suggestion.result['criteria'] if (c['question_id'], c['criterion_id']) == (d['question_id'], d['criterion_id']))
                        group['evidence'].append({'submission_id': submission.id, 'assignment_id': submission.assignment_id,
                            'criterion_id': d['criterion_id'], 'decision_id': review.id, 'interpretation_id': suggestion.interpretation_id,
                            'source': finding['evidence']})
        return {'items': list(groups.values()), 'denominator': 'Distinct submissions with an accepted teacher decision for this explicit category/tag; latest decisions supersede earlier reviews. No AI-only findings counted.'}
