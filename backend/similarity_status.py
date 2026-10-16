"""Shared receipt validation for the report and assignment register."""
from sqlalchemy import select
from persistence import AcademicSubmission, OriginalityAnalysis, OriginalityReport


def similarity_summary(submission, reports, receipt, candidates):
    from academic_api import _valid_similarity_report, _tokens, MIN_MATCH_TOKENS
    valid = all(_valid_similarity_report(r, submission, candidates.get(r.candidate_submission_id)) for r in reports)
    state = receipt.status if receipt else ('completed' if reports and valid else 'incomplete' if reports else 'missing')
    if not valid:
        state = 'incomplete'
    eligible = receipt.eligible_token_count if receipt else (reports[0].eligible_token_count if reports else None)
    if state == 'completed' and (not eligible or eligible < MIN_MATCH_TOKENS or
        eligible != len(_tokens(submission.extracted_text)[0]) or
        (receipt and (receipt.candidate_count < 1 or not receipt.completed_at or receipt.report_count != len(reports)))):
        state = 'incomplete'
    return {'analysis_status': state, 'match_ratio': max((r.match_ratio for r in reports), default=0) if state == 'completed' else None,
            'eligible_token_count': eligible, 'candidate_count': receipt.candidate_count if receipt else None}


def similarity_summaries(db, submissions):
    ids = [s.id for s in submissions]
    receipts = {r.submission_id: r for r in db.scalars(select(OriginalityAnalysis).where(OriginalityAnalysis.submission_id.in_(ids)))}
    reports = list(db.scalars(select(OriginalityReport).where(OriginalityReport.submission_id.in_(ids))))
    candidates = {s.id: s for s in db.scalars(select(AcademicSubmission).where(AcademicSubmission.id.in_({r.candidate_submission_id for r in reports})))}
    grouped = {}
    for r in reports:
        grouped.setdefault(r.submission_id, []).append(r)
    return {s.id: similarity_summary(s, grouped.get(s.id, []), receipts.get(s.id), candidates) for s in submissions}
