"""Operator-only, explicit ownership transfer. Never run automatically at startup.

Run from backend after a backup:
  .venv/bin/python scripts/claim_legacy_course.py COURSE_ID verified@example.com
Historical IDs, students and grades remain intact. The previous shared legacy
administrator loses teaching access to this course after ownership is assigned.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from persistence import AcademicCourse, SessionLocal
from account_models import Account, CourseOwner


def claim(course_id, email):
    with SessionLocal() as db:
        course = db.get(AcademicCourse, course_id)
        account = db.scalar(select(Account).where(Account.email == email.strip().casefold(), Account.verified.is_(True), Account.status == "active"))
        if not course or not account:
            raise SystemExit("Existing course and verified active account required.")
        if db.get(CourseOwner, course_id):
            raise SystemExit("Course already has an owner; refusing to overwrite ownership.")
        db.add(CourseOwner(course_id=course.id, account_id=account.id, public_code=course.code))
        db.commit()
        print("Ownership assigned. Existing academic records were retained.")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: claim_legacy_course.py COURSE_ID VERIFIED_EMAIL")
    claim(sys.argv[1], sys.argv[2])
