import secrets
from typing import Literal
from datetime import timedelta
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, delete
from account_models import Account, CourseOwner, AssignmentOwner
from institution_models import AccountRole, Institution, InstitutionMembership, CourseInstitution, TeacherInvitation, AuditEvent
from persistence import SessionLocal, CourseEnrollment, now_utc
from auth import request_user
from accounts import EmailPayload, account_identity, digest, rate_limit, require_email
from email_delivery import enqueue_action

router = APIRouter(prefix='/api/institutions', tags=['Institution administration'])
TEACHING_ROLES = {'teacher', 'school_admin', 'platform_admin', 'migration_pending'}

def effective_role(db, account_id):
    role = db.get(AccountRole, account_id)
    if role:
        return role.role
    # Preserve only previously-owned resources pending an explicit operator review.
    owns = db.scalar(select(CourseOwner.course_id).where(CourseOwner.account_id == account_id)) or db.scalar(select(AssignmentOwner.assignment_id).where(AssignmentOwner.account_id == account_id))
    return 'migration_pending' if owns else 'student'

def audit(db, user, action, resource, details=None):
    db.add(AuditEvent(actor=user.username if hasattr(user, 'username') else user, action=action, resource_id=resource, details=details or {}))

def membership(db, account_id, institution_id, roles):
    return db.scalar(select(InstitutionMembership).where(InstitutionMembership.account_id == account_id, InstitutionMembership.institution_id == institution_id, InstitutionMembership.status == 'active', InstitutionMembership.role.in_(roles)))

def require_institution(db, user, institution_id, admin=False):
    if not db.get(Institution, institution_id):
        raise HTTPException(404, 'Institution not found.')
    if user.role == 'platform_admin':
        return
    allowed = {'school_admin'} if admin else {'teacher', 'school_admin'}
    if user.role not in allowed or not membership(db, user.account_id, institution_id, allowed):
        raise HTTPException(403, 'Institution permission required.')

class InstitutionCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=200)

class Invite(EmailPayload):
    pass

class Accept(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(min_length=20, max_length=100)
    confirm_role_transition: bool = False

@router.get('')
def list_institutions(request: Request):
    identity = account_identity(request)
    user = request_user(request)
    with SessionLocal() as db:
        query = select(Institution)
        if user.role != 'platform_admin':
            query = query.join(InstitutionMembership).where(InstitutionMembership.account_id == identity, InstitutionMembership.status == 'active')
        return {'items': [{'id': row.id, 'name': row.name} for row in db.scalars(query)]}

@router.post('', status_code=201)
def create_institution(payload: InstitutionCreate, request: Request):
    user = request_user(request)
    if user.role != 'platform_admin':
        raise HTTPException(403, 'Platform administrator required.')
    if not payload.name.strip():
        raise HTTPException(422, 'Institution name required.')
    with SessionLocal() as db:
        row = Institution(name=payload.name.strip()); db.add(row); db.flush()
        audit(db, user, 'institution.create', row.id); db.commit()
        return {'id': row.id, 'name': row.name}

@router.post('/{institution_id}/teachers/invite', status_code=202)
def invite_teacher(institution_id: str, payload: Invite, request: Request):
    user = request_user(request)
    if user.role not in {'school_admin','platform_admin'}:
        raise HTTPException(403,'Institution administrator required.')
    rate_limit(request, 'teacher-invitation', user.account_id or user.username, 10)
    require_email()
    with SessionLocal() as db:
        require_institution(db, user, institution_id, admin=True)
        account = db.scalar(select(Account).where(Account.email == payload.email, Account.status == 'active'))
        if not account:
            raise HTTPException(409, 'The teacher must first register an account. Invitation acceptance requires verified email.')
        current_role = effective_role(db, account.id)
        if current_role in {'school_admin', 'platform_admin'}:
            raise HTTPException(409, 'Privileged accounts require operator review.')
        token = secrets.token_urlsafe(32)
        db.execute(delete(TeacherInvitation).where(TeacherInvitation.account_id == account.id, TeacherInvitation.institution_id == institution_id))
        db.add(TeacherInvitation(token_hash=digest(token), account_id=account.id, institution_id=institution_id, invited_by=user.account_id, expires_at=now_utc() + timedelta(hours=1)))
        enqueue_action(db, account, 'teacher_invite', token)
        audit(db, user, 'teacher.invite', account.id, {'institution_id': institution_id})
        db.commit()
    return {'message': 'Teacher invitation queued for delivery. No role has changed yet.'}

@router.post('/invitations/accept')
def accept_invitation(payload: Accept, request: Request):
    identity = account_identity(request)
    user = request_user(request)
    rate_limit(request, 'accept-invitation', identity, 10)
    if not payload.confirm_role_transition:
        raise HTTPException(409, 'Explicit role transition confirmation is required.')
    with SessionLocal() as db:
        # Claim and consume atomically; a rollback leaves a rejected invitation usable.
        invitation = db.execute(delete(TeacherInvitation).where(TeacherInvitation.token_hash == digest(payload.token), TeacherInvitation.account_id == identity, TeacherInvitation.expires_at > now_utc()).returning(TeacherInvitation.institution_id, TeacherInvitation.invited_by)).first()
        if not invitation:
            raise HTTPException(400, 'Invalid, expired or already used invitation.')
        inviter = db.get(Account, invitation.invited_by)
        inviter_role = effective_role(db, inviter.id) if inviter else None
        authorized = inviter_role == 'platform_admin' or (inviter_role == 'school_admin' and membership(db, inviter.id, invitation.institution_id, {'school_admin'}))
        if not inviter or not inviter.verified or inviter.status != 'active' or not authorized:
            raise HTTPException(403, 'Inviter is no longer authorized.')
        # Strict separation: do not silently retain active student enrollments.
        rows = db.scalars(select(CourseEnrollment).where(CourseEnrollment.student_id == identity)).all()
        from permissions import enrollment_active
        if any(enrollment_active(db, row) for row in rows):
            raise HTTPException(409, 'Active student memberships require administrator review before promotion.')
        if effective_role(db, identity) in {'school_admin', 'platform_admin'}:
            raise HTTPException(409, 'Privileged role changes require operator review.')
        role = db.get(AccountRole, identity)
        if role: role.role = 'teacher'
        else: db.add(AccountRole(account_id=identity, role='teacher'))
        member = db.scalar(select(InstitutionMembership).where(InstitutionMembership.account_id == identity, InstitutionMembership.institution_id == invitation.institution_id))
        if member: member.role = 'teacher'; member.status = 'active'
        else: db.add(InstitutionMembership(account_id=identity, institution_id=invitation.institution_id, role='teacher'))
        audit(db, user, 'teacher.invitation.accept', identity, {'institution_id': invitation.institution_id})
        db.commit()
    return {'message': 'Teacher access approved. Reload your session to use the teacher workspace.'}

class MembershipUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['active', 'suspended']

@router.get('/{institution_id}/teachers')
def teachers(institution_id: str, request: Request):
    user=request_user(request)
    with SessionLocal() as db:
        require_institution(db,user,institution_id,admin=True)
        rows=db.execute(select(InstitutionMembership,Account).join(Account,Account.id==InstitutionMembership.account_id).where(InstitutionMembership.institution_id==institution_id,InstitutionMembership.role=='teacher')).all()
        return {'items':[{'id':member.id,'name':account.display_name,'email':account.email,'status':member.status} for member,account in rows]}

@router.patch('/{institution_id}/teachers/{membership_id}')
def update_teacher(institution_id:str,membership_id:str,payload:MembershipUpdate,request:Request):
    user=request_user(request)
    with SessionLocal() as db:
        require_institution(db,user,institution_id,admin=True)
        row=db.get(InstitutionMembership,membership_id)
        if not row or row.institution_id!=institution_id or row.role!='teacher':
            raise HTTPException(404,'Teacher membership not found.')
        row.status=payload.status
        audit(db,user,'teacher.membership.update',row.id,{'institution_id':institution_id,'status':payload.status})
        db.commit()
    return {'message':'Teacher membership updated. Account role and historical data were retained.'}

@router.patch('/{institution_id}')
def update_institution(institution_id:str,payload:InstitutionCreate,request:Request):
    user=request_user(request)
    with SessionLocal() as db:
        require_institution(db,user,institution_id,admin=True)
        if not payload.name.strip():raise HTTPException(422,'Institution name required.')
        row=db.get(Institution,institution_id);row.name=payload.name.strip()
        audit(db,user,'institution.rename',institution_id);db.commit()
    return {'message':'Institution name updated.'}
