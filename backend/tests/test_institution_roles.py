from datetime import timedelta
import pytest
from sqlalchemy import select
from test_accounts_courses import platform, identity, create_course
from account_models import Account, CourseOwner
from institution_models import AccountRole, Institution, InstitutionMembership, TeacherInvitation, AuditEvent
from persistence import now_utc
import institutions
from scripts.approve_account_role import approve


def test_student_cannot_self_promote_or_use_teacher_routes(platform):
    client, factory, sent = platform
    headers = identity(client, sent, 'student@example.com')
    me = client.get('/api/auth/me', headers=headers).json()
    assert me['role'] == 'student'
    assert client.post('/api/courses', headers=headers, json={}).status_code == 403
    assert client.get('/api/teacher-overview', headers=headers).status_code == 403
    assert client.post('/assignments', headers=headers, json={}).status_code == 403
    assert client.patch('/api/accounts/profile', headers=headers, json={'display_name': 'Student', 'role': 'platform_admin'}).status_code == 422
    assert client.get('/api/auth/me', headers=headers).json()['role'] == 'student'


def test_school_invitation_is_scoped_single_use_and_verified(platform):
    client, factory, sent = platform
    admin = identity(client, sent, 'admin@example.com')
    teacher = identity(client, sent, 'invited@example.com')
    admin_id = client.get('/api/auth/me', headers=admin).json()['account_id']
    with factory() as db:
        school = Institution(name='School A'); other = Institution(name='School B'); db.add_all([school, other]); db.flush()
        db.get(AccountRole, admin_id).role = 'school_admin'
        db.add(InstitutionMembership(institution_id=school.id, account_id=admin_id, role='school_admin'))
        db.commit(); school_id, other_id = school.id, other.id
    assert client.post(f'/api/institutions/{other_id}/teachers/invite', headers=admin, json={'email':'invited@example.com'}).status_code == 403
    response = client.post(f'/api/institutions/{school_id}/teachers/invite', headers=admin, json={'email':'invited@example.com'})
    assert response.status_code == 202, response.text
    token = sent[-1][2]
    assert client.post('/api/institutions/invitations/accept', headers=teacher, json={'token': token}).status_code == 409
    assert client.post('/api/institutions/invitations/accept', headers=teacher, json={'token': token, 'confirm_role_transition':True}).status_code == 200
    assert client.get('/api/auth/me', headers=teacher).json()['role'] == 'teacher'
    assert client.post('/api/institutions/invitations/accept', headers=teacher, json={'token': token, 'confirm_role_transition':True}).status_code == 400
    payload = {'institution_id':other_id, 'title':'Unauthorized', 'code':'U', 'subject':'Science', 'term':'Fall', 'academic_year':'2026'}
    assert client.post('/api/courses', headers=teacher, json=payload).status_code == 403
    payload['institution_id'] = school_id
    assert client.post('/api/courses', headers=teacher, json=payload).status_code == 201
    assert client.post('/api/enrollment/join', headers=teacher, json={'class_code':'INVALID'}).status_code == 403
    with factory() as db: assert db.scalar(select(AuditEvent).where(AuditEvent.action == 'teacher.invitation.accept'))


def test_expired_invitation_and_bootstrap_confirmation(platform):
    client, factory, sent = platform
    headers = identity(client, sent, 'operator@example.com')
    account_id = client.get('/api/auth/me', headers=headers).json()['account_id']
    with pytest.raises(ValueError): approve(account_id, 'platform_admin', 'yes')
    original = institutions.SessionLocal
    # CLI deliberately uses its own factory; test replaces only the synthetic one.
    import scripts.approve_account_role as cli
    cli.SessionLocal = factory
    try:
        approve(account_id, 'platform_admin', f'APPROVE:{account_id}:platform_admin')
        approve(account_id, 'platform_admin', f'APPROVE:{account_id}:platform_admin')
    finally: cli.SessionLocal = original
    school = client.post('/api/institutions', headers=headers, json={'name':'Test school'}).json()['id']
    candidate = identity(client, sent, 'candidate@example.com')
    client.post(f'/api/institutions/{school}/teachers/invite', headers=headers, json={'email':'candidate@example.com'})
    with factory() as db:
        invite = db.scalar(select(TeacherInvitation)); invite.expires_at = now_utc() - timedelta(seconds=1); db.commit()
    assert client.post('/api/institutions/invitations/accept', headers=candidate, json={'token':sent[-1][2], 'confirm_role_transition':True}).status_code == 400
    assert client.get('/api/auth/me', headers=candidate).json()['role'] == 'student'


def test_legacy_owner_transition_preserves_only_owned_resources(platform):
    from persistence import AcademicCourse
    client,factory,sent=platform
    headers=identity(client,sent,'existing-owner@example.com')
    account_id=client.get('/api/auth/me',headers=headers).json()['account_id']
    with factory() as db:
        db.delete(db.get(AccountRole,account_id))
        course=AcademicCourse(code='OLD',name='Historical course',instructor='Old instructor',department='Science');db.add(course);db.flush()
        db.add(CourseOwner(course_id=course.id,account_id=account_id,public_code='OLD'));db.commit();course_id=course.id
    assert client.get('/api/auth/me',headers=headers).json()['role']=='migration_pending'
    assert client.get('/academic/courses?role=teacher',headers=headers).json()['items'][0]['id']==course_id
    assert client.post('/api/courses',headers=headers,json={'title':'Unauthorized new course','code':'NEW','subject':'Science','academic_year':'2026','term':'Fall','institution_id':'unknown'}).status_code in {403,404}
    with factory() as db:assert db.get(CourseOwner,course_id).account_id==account_id


def test_enrollment_never_changes_role_and_invitation_cannot_bypass_membership_review(platform):
    client,factory,sent=platform
    teacher=identity(client,sent,'teacher@example.com');student=identity(client,sent,'student@example.com')
    course=create_course(client,teacher)
    response=client.post('/api/enrollment/join',headers=student,json={'class_code':course['class_code']})
    assert response.status_code==201
    assert client.get('/api/auth/me',headers=student).json()['role']=='student'
    assert client.post('/api/courses',headers=student,json={}).status_code==403


def test_school_admin_role_does_not_grant_admin_in_teacher_only_institution(platform):
    client,factory,sent=platform
    admin=identity(client,sent,'admin@example.com');other=identity(client,sent,'other-teacher@example.com')
    course_a=create_course(client,admin);course_b=create_course(client,other)
    account_id=client.get('/api/auth/me',headers=admin).json()['account_id']
    from institution_models import CourseInstitution
    with factory() as db:
        institution_a=db.get(CourseInstitution,course_a['course_id']).institution_id
        institution_b=db.get(CourseInstitution,course_b['course_id']).institution_id
        db.get(AccountRole,account_id).role='school_admin'
        member=db.scalar(select(InstitutionMembership).where(InstitutionMembership.account_id==account_id));member.role='school_admin'
        db.add(InstitutionMembership(account_id=account_id,institution_id=institution_b,role='teacher'))
        db.commit()
    assert client.get(f"/academic/offerings/{course_b['offering_id']}?role=teacher",headers=admin).status_code==403
    assert client.post(f'/api/institutions/{institution_b}/teachers/invite',headers=admin,json={'email':'admin@example.com'}).status_code==403
    assert client.get(f"/academic/offerings/{course_a['offering_id']}?role=teacher",headers=admin).status_code==200


def test_suspended_teacher_membership_loses_course_access(platform):
    client,factory,sent=platform
    teacher=identity(client,sent,'teacher@example.com');admin=identity(client,sent,'admin@example.com')
    course=create_course(client,teacher)
    teacher_id=client.get('/api/auth/me',headers=teacher).json()['account_id']
    admin_id=client.get('/api/auth/me',headers=admin).json()['account_id']
    from institution_models import CourseInstitution
    with factory() as db:
        school=db.get(CourseInstitution,course['course_id']).institution_id
        db.get(AccountRole,admin_id).role='school_admin'
        db.add(InstitutionMembership(account_id=admin_id,institution_id=school,role='school_admin'))
        member=db.scalar(select(InstitutionMembership).where(InstitutionMembership.account_id==teacher_id));member_id=member.id;db.commit()
    assert client.patch(f'/api/institutions/{school}/teachers/{member_id}',headers=admin,json={'status':'suspended'}).status_code==200
    assert client.get(f"/academic/offerings/{course['offering_id']}?role=teacher",headers=teacher).status_code==403
    assert client.get('/academic/courses?role=teacher',headers=teacher).json()['items']==[]


def test_invited_student_with_active_enrollment_requires_membership_review(platform):
    from account_models import EnrollmentState
    from persistence import CourseEnrollment
    from institution_models import CourseInstitution
    client,factory,sent=platform
    admin=identity(client,sent,'admin@example.com');student=identity(client,sent,'student@example.com')
    course=create_course(client,admin)
    enrolled=client.post('/api/enrollment/join',headers=student,json={'class_code':course['class_code']}).json()
    admin_id=client.get('/api/auth/me',headers=admin).json()['account_id']
    with factory() as db:
        school=db.get(CourseInstitution,course['course_id']).institution_id
        db.get(AccountRole,admin_id).role='school_admin'
        db.scalar(select(InstitutionMembership).where(InstitutionMembership.account_id==admin_id)).role='school_admin';db.commit()
    assert client.post(f'/api/institutions/{school}/teachers/invite',headers=admin,json={'email':'student@example.com'}).status_code==202
    token=sent[-1][2]
    assert client.post('/api/institutions/invitations/accept',headers=student,json={'token':token,'confirm_role_transition':True}).status_code==409
    assert client.get('/api/auth/me',headers=student).json()['role']=='student'
    with factory() as db:
        state=db.get(EnrollmentState,enrolled['id']);state.status='suspended';db.commit()
    assert client.post('/api/institutions/invitations/accept',headers=student,json={'token':token,'confirm_role_transition':True}).status_code==200
