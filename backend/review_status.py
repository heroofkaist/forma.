"""Read-only human review summaries, independent of inference jobs."""
import math
from sqlalchemy import select
from document_models import DocumentReview, PublishedDocumentReview
from persistence import AcademicGrade


def confirmed_review(review, assignment):
    expected = {(q['id'], c['criterion_id']): c['maximum_points']
                for q in assignment.questions for c in q['criteria']}
    scores = review.criteria or []
    keys = [(s.get('question_id'), s.get('criterion_id')) for s in scores]
    return (bool(expected) and len(keys) == len(set(keys)) and set(keys) == set(expected) and
            all(s.get('confirmed') is not False and isinstance(s.get('points'), (int, float)) and
                math.isfinite(s['points']) and 0 <= s['points'] <= expected[key]
                for key, s in zip(keys, scores)) and
            sum(s['points'] for s in scores) <= assignment.maximum_score)


def review_summaries(db, assignment, submission_ids):
    reviews = db.scalars(select(DocumentReview).where(DocumentReview.submission_id.in_(submission_ids))
                         .order_by(DocumentReview.created_at.desc(), DocumentReview.id.desc())).all()
    latest, confirmed = {}, {}
    for review in reviews:
        latest.setdefault(review.submission_id, review)
        if confirmed_review(review, assignment):
            confirmed.setdefault(review.submission_id, review)
    grades = {g.submission_id: g for g in db.scalars(select(AcademicGrade).where(
        AcademicGrade.submission_id.in_(submission_ids), AcademicGrade.published.is_(True)))}
    result = {}
    for sid in submission_ids:
        grade, review, last = grades.get(sid), confirmed.get(sid), latest.get(sid)
        link = db.get(PublishedDocumentReview, grade.id) if grade else None
        result[sid] = {
            'review_status': 'published' if grade else 'confirmed' if review else 'draft' if last else 'unreviewed',
            'review_points': grade.points if grade else sum(s['points'] for s in review.criteria) if review else None,
            'review_maximum': grade.maximum_score if grade else assignment.maximum_score,
            'review_id': link.review_id if link else review.id if review else None,
            'has_draft': bool(last and not confirmed_review(last, assignment)),
            'published_grade': {'points': grade.points, 'maximum_score': grade.maximum_score,
                                'published_at': grade.published_at.isoformat() if grade.published_at else None,
                                'review_id': link.review_id if link else None} if grade else None,
        }
    return result
