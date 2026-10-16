"""Bounded, anonymous teacher examples passed as policy, never student evidence."""
from sqlalchemy import select
from teaching_models import TeachingGuide
from document_models import DocumentReview
from persistence import AcademicSubmission
from fastapi import HTTPException


def normalized_questions(questions):
    return [{**q, 'criteria': [{**c, 'partial_credit': c.get('partial_credit', ''),
        'evidence_expected': c.get('evidence_expected', '')} for c in q['criteria']]} for q in questions]


def current_questions(db, assignment):
    from assessment_models import AssessmentRubric
    from review_pilot import questions_for_spec
    from services.assessment import rubric_for_assignment
    row = db.scalar(select(AssessmentRubric).where(AssessmentRubric.assignment_id == assignment.id)
        .order_by(AssessmentRubric.created_at.desc(), AssessmentRubric.id.desc()).limit(1))
    if row:
        try:
            rubric_for_assignment(row.spec, assignment)
            return normalized_questions(questions_for_spec(assignment, row.spec))
        except ValueError: pass
    return normalized_questions(assignment.questions)


def rubric_key(db, assignment):
    from review_pilot import digest
    return digest({'category': assignment.assignment_type, 'description': assignment.description,
        'questions': current_questions(db, assignment)})


def compatible_review(db, review, assignment):
    import math
    from review_pilot import signature
    questions = current_questions(db, assignment)
    expected = {(q['id'], c['criterion_id']): c['maximum_points'] for q in questions for c in q['criteria']}
    if not review or len(review.criteria) != len(expected): return False
    keys = [(c['question_id'], c['criterion_id']) for c in review.criteria]
    if len(set(keys)) != len(expected) or set(keys) != set(expected): return False
    try:
        return all(c.get('confirmed') is not False and not isinstance(c.get('points'), bool)
            and isinstance(c.get('points'), (int, float)) and math.isfinite(c['points'])
            and 0 <= c['points'] <= expected[(c['question_id'], c['criterion_id'])]
            and signature(assignment, c['question_id'], c['criterion_id'], normalized_questions(review.rubric_snapshot or []))
                == signature(assignment, c['question_id'], c['criterion_id'], questions) for c in review.criteria)
    except (KeyError, TypeError, HTTPException): return False


def latest_guide(db, assignment_id):
    return db.scalar(select(TeachingGuide).where(TeachingGuide.assignment_id == assignment_id)
        .order_by(TeachingGuide.created_at.desc(), TeachingGuide.id.desc()).limit(1))


def guide_snapshot(db, assignment, exclude_sid=None):
    row = latest_guide(db, assignment.id)
    if not row: return {'id': None, 'rules': [], 'examples': []}
    if row.content.get('rubric_key') != rubric_key(db, assignment):
        return {'id': row.id, 'rules': [], 'examples': [], 'stale': True}
    examples = []
    from processing_models import DocumentInterpretation
    for rid in row.content['reference_review_ids']:
        review = db.get(DocumentReview, rid)
        submission = db.get(AcademicSubmission, review.submission_id) if review else None
        if not submission or submission.assignment_id != assignment.id or submission.id == exclude_sid or not compatible_review(db, review, assignment): continue
        source = db.scalar(select(DocumentInterpretation).where(DocumentInterpretation.submission_id == submission.id)
            .order_by(DocumentInterpretation.created_at.desc()).limit(1))
        from document_models import SubmissionDocument
        from processing_models import ProcessingJob, InterpretationCorrection
        document = db.get(SubmissionDocument, submission.id)
        job = db.get(ProcessingJob, source.job_id) if source else None
        correction = db.scalar(select(InterpretationCorrection).where(InterpretationCorrection.interpretation_id == source.id)
            .order_by(InterpretationCorrection.created_at.desc()).limit(1)) if source else None
        observed_source = correction.result if correction else source.result if source else {}
        valid_source = bool(job and document and job.content_hash == document.content_hash and not job.usage.get('partial'))
        def anonymous(value):
            for identity in (submission.student_name, submission.student_id):
                if identity and len(identity) > 2: value = value.replace(identity, '[студент]')
            return value
        for c in review.criteria:
            if c.get('confirmed') is False or c.get('points') is None: continue
            sections = observed_source.get('sections', []) if valid_source else []
            observed = '\n'.join(s.get('transcription', '') for s in sections if s.get('question_id') == c['question_id']
                and (not s.get('criterion_ids') or c['criterion_id'] in s['criterion_ids']))[:400]
            examples.append({'question_id': c['question_id'], 'criterion_id': c['criterion_id'],
                'teacher_score': c['points'], 'teacher_comment': anonymous(c.get('comment', '')[:350]), 'example_answer': anonymous(observed)})
    return {'id': row.id, 'rules': row.content['rules'], 'examples': examples,
        'feedback_focus': row.content.get('feedback_focus', '')}


def batch_guidance(snapshot, criteria):
    keys = {(c['question_id'], c['criterion_id']) for c in criteria}
    guide = snapshot.get('teaching_guide', {})
    rules = [r for r in guide.get('rules', []) if (r['question_id'], r['criterion_id']) in keys]
    examples = [e for e in guide.get('examples', []) if (e['question_id'], e['criterion_id']) in keys][:3]
    return {'rules': rules, 'reference_examples': examples, 'feedback_focus': guide.get('feedback_focus', ''),
        'examples_are_not_current_student_evidence': True}
