"""Explicit operator-only role approval; never invoked by web requests/startup."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from persistence import SessionLocal, CourseEnrollment
from account_models import Account, CourseOwner, EnrollmentState
from institution_models import AccountRole, Institution, InstitutionMembership, CourseInstitution
from institutions import audit, effective_role
from permissions import enrollment_active


def approve(account_id, role, confirmation, institution_id=None, review_enrollments=False, course_id=None):
    if confirmation != f'APPROVE:{account_id}:{role}':
        raise ValueError('Explicit confirmation must match the exact account ID and role.')
    with SessionLocal() as db:
        account = db.get(Account, account_id)
        if not account or not account.verified or account.status != 'active':
            raise ValueError('An exact verified active account ID is required.')
        if role != 'platform_admin' and not db.get(Institution, institution_id):
            raise ValueError('An existing authorized institution ID is required.')
        active = [row for row in db.scalars(select(CourseEnrollment).where(CourseEnrollment.student_id == account_id)) if enrollment_active(db, row)]
        if active and not review_enrollments:
            raise ValueError('Active student enrollments require explicit --review-enrollments. They will be suspended, preserving records.')
        previous = effective_role(db, account_id)
        for row in active:
            state = db.get(EnrollmentState, row.id)
            if state: state.status = 'suspended'
            else: db.add(EnrollmentState(enrollment_id=row.id, status='suspended'))
            audit(db, 'operator-cli', 'enrollment.role_transition.suspend', row.id)
        access = db.get(AccountRole, account_id)
        if access: access.role = role
        else: db.add(AccountRole(account_id=account_id, role=role))
        if institution_id:
            member = db.scalar(select(InstitutionMembership).where(InstitutionMembership.account_id == account_id, InstitutionMembership.institution_id == institution_id))
            if member: member.role = role; member.status = 'active'
            else: db.add(InstitutionMembership(account_id=account_id, institution_id=institution_id, role=role))
        if course_id:
            owner = db.get(CourseOwner, course_id)
            if not institution_id or not owner or owner.account_id != account_id:
                raise ValueError('Only this account’s existing owned course can be explicitly assigned to the institution.')
            tenant = db.get(CourseInstitution, course_id)
            if tenant and tenant.institution_id != institution_id:
                raise ValueError('Refusing to transfer a course from another institution.')
            if not tenant: db.add(CourseInstitution(course_id=course_id, institution_id=institution_id))
        audit(db, 'operator-cli', 'account.role.approve', account_id, {'previous': previous, 'role': role, 'institution_id': institution_id, 'course_id': course_id})
        db.commit()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('account_id'); parser.add_argument('role', choices=['teacher', 'school_admin', 'platform_admin'])
    parser.add_argument('--confirm', required=True); parser.add_argument('--institution'); parser.add_argument('--review-enrollments', action='store_true'); parser.add_argument('--claim-course')
    args = parser.parse_args()
    try: approve(args.account_id, args.role, args.confirm, args.institution, args.review_enrollments, args.claim_course)
    except ValueError as error: raise SystemExit(str(error))
    print('Explicit role approval recorded; no secrets printed.')
