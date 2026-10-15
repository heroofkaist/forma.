"""Synthetic age and guardian registration flows: no SMTP, AI or real child data."""
import hashlib
import hmac
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select, func
from test_accounts_courses import platform, registration_age
from account_models import GuardianRegistration, Account, EmailOutbox, AccountSession
from auth import _secret
import accounts
import age_screen
import guardian_registration as guardian
from email_delivery import cipher
from persistence import now_utc


@pytest.fixture
def enabled(platform, monkeypatch):
    monkeypatch.setenv('FORMA_GUARDIAN_REGISTRATION_ENABLED','true')
    monkeypatch.setenv('FORMA_GUARDIAN_PRIVACY_NOTICE_URL','https://forma.example/privacy')
    monkeypatch.setenv('FORMA_GUARDIAN_PRIVACY_CONTACT','privacy@example.test')
    return platform


def teen(client):
    result=client.post('/api/accounts/age-check',json={'age_band':'13_to_17'})
    assert result.status_code==200 and result.json()['next_step']=='guardian'
    return result.json()['age_check_token']


def request(client, token, email='parent@example.test'):
    result=client.post('/api/accounts/guardian-consent/request',json={'email':email,'age_check_token':token})
    assert result.status_code==202,result.text
    return result.json()


def parent_link(factory):
    with factory() as db:
        row=db.scalar(select(GuardianRegistration))
        return cipher().decrypt(row.encrypted_token.encode()).decode()


def approve(client, token):
    return client.post('/api/accounts/guardian-consent/decision',json={'token':token,'decision':'approve','adult_guardian':True,'consent':True})


def signup(token, email='teen@example.test'):
    return {'email':email,'display_name':'Synthetic teen','password':'Synthetic-password-123','age_check_token':token}


def test_adult_can_replace_legacy_accidental_block_but_current_minor_cannot_flip_age(platform):
    client,factory,sent=platform
    # Reproduce the previous release's cookie, including the original signature.
    body='v1.blocked.'+str(int(age_screen.time.time()))+'.'+'a'*32
    token=body+'.'+hmac.new(_secret(),('age-screen:'+body).encode(),hashlib.sha256).hexdigest()
    client.cookies.set(age_screen.COOKIE,token)
    proof=registration_age(client)
    assert proof.startswith('v2.eligible.')
    assert client.post('/api/accounts/register',json=signup(proof,'adult-recovery@example.test')).status_code==202
    client.cookies.clear()
    current=teen(client)
    assert client.post('/api/accounts/age-check',json={'age_band':'18_or_over'}).json()['age_check_token']==current
    assert client.post('/api/accounts/register',json=signup(current)).status_code in (403,503)


def test_teen_requires_parent_approval_and_separate_verified_child_email(enabled, monkeypatch):
    client,factory,sent=enabled
    token=teen(client)
    assert client.post('/api/accounts/register',json=signup(token)).status_code==403
    data=request(client,token); parent=parent_link(factory)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Account))==0
        row=db.scalar(select(GuardianRegistration))
        assert 'parent@example.test' not in row.encrypted_email and parent not in row.encrypted_token
        assert row.status=='pending' and row.notice_version and row.notice_text
    # Merely opening the link never grants permission.
    inspect=client.post('/api/accounts/guardian-consent/inspect',json={'token':parent})
    assert inspect.status_code==200 and inspect.json()['status']=='pending'
    assert inspect.json()['request_code']==data['request_code']
    assert client.post('/api/accounts/register',json=signup(token)).status_code==403
    assert client.post('/api/accounts/guardian-consent/decision',json={'token':parent,'decision':'approve'}).status_code==422
    assert approve(client,parent).status_code==200
    assert approve(client,parent).status_code==409
    assert client.post('/api/accounts/guardian-consent/status',json={'age_check_token':token}).json()['status']=='approved'
    assert client.post('/api/accounts/register',json=signup(token,'parent@example.test')).status_code==422
    assert client.post('/api/accounts/register',json=signup(token)).status_code==202
    assert client.post('/api/accounts/register',json=signup(token,'another-teen@example.test')).status_code==403
    with factory() as db:
        account=db.scalar(select(Account));permission=db.scalar(select(GuardianRegistration))
        assert account.email=='teen@example.test' and not account.verified
        assert permission.account_id==account.id and permission.status=='consumed'
        assert permission.approved_at
    assert sent[-1][0:2]==('teen@example.test','verify')
    assert client.post('/api/auth/login',json={'role':'student','username':'teen@example.test','password':'Synthetic-password-123'}).status_code==401
    assert client.post('/api/accounts/verify-email',json={'token':sent[-1][2]}).status_code==200
    result=client.post('/api/auth/login',json={'role':'student','username':'teen@example.test','password':'Synthetic-password-123'})
    assert result.status_code==200
    headers={'Authorization':'Bearer '+result.json()['access_token']}
    # The parent can withdraw during the link lifetime; child sessions close, records aren't deleted.
    assert client.post('/api/accounts/guardian-consent/decision',json={'token':parent,'decision':'decline'}).status_code==200
    assert client.get('/api/auth/me',headers=headers).status_code==401
    with factory() as db:
        assert db.scalar(select(Account)).status=='consent_revoked'
        assert db.scalar(select(func.count()).select_from(AccountSession))==0


def test_parent_decline_expiry_tampering_and_cross_browser_binding(enabled):
    client,factory,_=enabled
    token=teen(client);request(client,token);parent=parent_link(factory)
    assert approve(client,parent[:-1]+'!').status_code==410
    client.cookies.clear()
    assert client.post('/api/accounts/guardian-consent/status',json={'age_check_token':token}).status_code==403
    client.cookies.set(age_screen.COOKIE,token)
    assert client.post('/api/accounts/guardian-consent/decision',json={'token':parent,'decision':'decline'}).status_code==200
    assert client.post('/api/accounts/register',json=signup(token)).status_code==403
    with factory() as db:
        row=db.scalar(select(GuardianRegistration));row.expires_at=now_utc()-timedelta(seconds=1);db.commit()
    assert approve(client,parent).status_code==410
    with factory() as db: assert db.scalar(select(func.count()).select_from(Account))==0


def test_guardian_mail_uses_existing_worker_with_lease_and_resend_rotation(enabled, monkeypatch):
    client,factory,_=enabled
    token=teen(client);request(client,token);old=parent_link(factory)
    assert client.post('/api/accounts/guardian-consent/request',json={'age_check_token':token,'email':'parent@example.test'}).status_code==429
    with factory() as db:
        db.scalar(select(GuardianRegistration)).created_at=now_utc()-timedelta(minutes=2);db.commit()
    request(client,token,'corrected-parent@example.test');new=parent_link(factory)
    assert new!=old and approve(client,old).status_code==410
    delivered=[]
    monkeypatch.setattr(accounts,'send_action',lambda *args:delivered.append(args))
    from email_delivery import deliver_one as deliver_mail
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:deliver_mail(),range(2)))
    assert sum(results)==1 and delivered==[('corrected-parent@example.test','guardian_consent',new)]
    with factory() as db:
        row=db.scalar(select(GuardianRegistration));assert row.delivery_status=='sent' and row.encrypted_token==''
    assert not guardian.deliver_one()
    assert approve(client,new).status_code==200


def test_feature_requires_real_notice_contact_and_does_not_open_under13(enabled, monkeypatch):
    client,factory,_=enabled
    monkeypatch.setenv('FORMA_GUARDIAN_PRIVACY_CONTACT','')
    assert not client.get('/api/accounts/status').json()['guardian_registration_enabled']
    token=teen(client)
    assert client.post('/api/accounts/guardian-consent/request',json={'age_check_token':token,'email':'parent@example.test'}).status_code==503
    client.cookies.clear()
    blocked=client.post('/api/accounts/age-check',json={'age_band':'under_13'}).json()
    assert blocked['next_step']=='blocked'
    assert client.post('/api/accounts/register',json=signup(blocked['age_check_token'])).status_code==403
    with factory() as db: assert db.scalar(select(func.count()).select_from(GuardianRegistration))==0


def test_postgresql_parent_permission_is_consumed_by_only_one_registration(enabled):
    import os
    from uuid import uuid4
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from persistence import Base, _normalize_database_url
    from fastapi import HTTPException
    url=os.getenv('FORMA_TEST_POSTGRESQL_URL')
    if not url: pytest.skip('Set a disposable local PostgreSQL URL for the guardian consumption race.')
    schema='forma_guardian_test_'+uuid4().hex
    root=create_engine(_normalize_database_url(url)); scoped=None
    try:
        with root.begin() as db: db.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        scoped=create_engine(_normalize_database_url(url),connect_args={'options':'-csearch_path='+schema})
        Base.metadata.create_all(scoped);factory=sessionmaker(scoped,expire_on_commit=False)
        proof='synthetic-browser-proof'
        with factory() as db:
            db.add(GuardianRegistration(proof_hash=accounts.digest(proof),token_hash=accounts.digest('parent-token'),
                encrypted_email=cipher().encrypt(b'parent@example.test').decode(),encrypted_token='',
                notice_url='https://forma.example/privacy',privacy_contact='privacy@example.test',notice_version=guardian.NOTICE_VERSION,
                notice_text=guardian.NOTICE,status='approved',approved_at=now_utc(),expires_at=now_utc()+timedelta(hours=1)))
            db.commit()
        def consume(index):
            with factory() as db:
                try:
                    permission=guardian.permission_for_registration(db,proof,f'synthetic-{index}@example.test')
                    account=Account(email=f'synthetic-{index}@example.test',display_name='Synthetic',password_hash='unused-in-test')
                    db.add(account);db.flush();permission.account_id=account.id;permission.status='consumed';db.commit()
                    return True
                except HTTPException as error:
                    assert error.status_code==403
                    db.rollback();return False
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(consume,range(2)))
        assert sum(results)==1
        with factory() as db: assert db.scalar(select(func.count()).select_from(Account))==1
    finally:
        if scoped: scoped.dispose()
        with root.begin() as db: db.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        root.dispose()
