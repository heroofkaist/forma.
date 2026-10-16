"""Durable reading → rubric assessment; a teacher request authorizes both stages."""
from sqlalchemy import select
from processing_models import DocumentInterpretation, InterpretationCorrection, ProcessingJob
from document_models import SubmissionDocument
from services.assignment_context import assignment_snapshot


def snapshot(db, submission, assignment, approved, source):
    source_job = db.get(ProcessingJob, source.job_id)
    document = db.get(SubmissionDocument, submission.id)
    if not source_job or not document or document.content_hash != source_job.content_hash:
        raise ValueError('Source observations do not match the current original document. Reanalyze before assessment.')
    if source_job.usage.get('partial'):
        raise ValueError('Partial document coverage cannot justify assessment scores. Review manually or analyze the complete bounded document.')
    correction = db.scalar(select(InterpretationCorrection).where(InterpretationCorrection.interpretation_id == source.id)
        .order_by(InterpretationCorrection.created_at.desc()).limit(1))
    observed = correction.result if correction else source.result
    from services.teaching_guidance import guide_snapshot
    return {'teaching_guide': guide_snapshot(db, assignment, exclude_sid=submission.id), 'rubric_id': approved.id, 'rubric': approved.spec, 'interpretation_id': source.id,
        'correction_id': correction.id if correction else None, 'title': assignment.title,
        'source': {'sections': [{k: s.get(k, [] if k == 'criterion_ids' else None)
            for k in ('id', 'page_number', 'question_id', 'criterion_ids', 'kind', 'transcription', 'readability', 'evidence_kind')}
            for s in observed['sections']]},
        'assignment_context': assignment_snapshot(db, assignment),
        'source_limitations': {'warnings': observed['warnings'], 'teacher_confirmed': bool(correction and correction.confirmed),
            'visual_transcription_unverified': not bool(correction and correction.confirmed),
            'external_facts_verified': False, 'code_executed': False,
            'assignment_reading_incomplete': bool(source_job.usage.get('assignment_context_shortened'))}}


def activate_waiting(db):
    """Called by the worker, so closing/reloading the browser cannot lose stage two."""
    from assessment_models import AssessmentRubric
    from persistence import AcademicSubmission, AcademicAssignment
    from services.assessment import rubric_for_assignment
    jobs = db.scalars(select(ProcessingJob).where(ProcessingJob.status == 'awaiting_source').with_for_update()).all()
    for job in jobs:
        parent = db.get(ProcessingJob, job.context['depends_on'])
        if parent and parent.status in {'queued', 'extracting', 'interpreting', 'awaiting_budget'}:
            continue
        try:
            if not parent or parent.status == 'failed':
                raise ValueError('Распознавание не завершено. Откройте помощь ИИ и проверьте состояние документа.')
            submission = db.get(AcademicSubmission, job.submission_id)
            assignment = db.get(AcademicAssignment, submission.assignment_id)
            approved = db.get(AssessmentRubric, job.context['rubric_id'])
            if not approved: raise ValueError('Критерии проверки недоступны. Запросите оценивание заново.')
            rubric_for_assignment(approved.spec, assignment)
            source = db.scalar(select(DocumentInterpretation).where(DocumentInterpretation.job_id == parent.id))
            if not source: raise ValueError('Результат распознавания недоступен. Повторите проверку.')
            job.context = {**job.context, 'assessment': snapshot(db, submission, assignment, approved, source)}
            job.status = job.stage = 'queued'
        except ValueError as error:
            job.status = job.stage = 'failed'
            job.error_class = 'assessment_source_unavailable'
            job.error = str(error)


def job_state(db, job):
    from services.assessment_errors import MESSAGES
    parent = db.get(ProcessingJob, job.context.get('depends_on')) if job.status == 'awaiting_source' else None
    paused = parent if parent and parent.status == 'awaiting_budget' else job
    return {'id': job.id, 'status': paused.status, 'error': paused.error,
        'error_hint': MESSAGES.get(paused.error_class)}

