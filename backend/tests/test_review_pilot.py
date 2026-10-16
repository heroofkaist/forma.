"""Synthetic teacher-memory, page-queue, receipt and export integration checks."""
import csv
import io
from copy import deepcopy
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from test_accounts_courses import platform, identity, create_course
from test_document_processing import setup_submission
from document_models import DocumentReview, SubmissionDocument, PublishedDocumentReview
from persistence import AcademicAssignment, AcademicSubmission, AcademicGrade, now_utc
from review_pilot_models import ReviewDecisionCard, QuestionPageMap, SubmissionUploadReceipt
import review_pilot
import academic_api
from test_assessment import assessed

@pytest.fixture
def pilot(platform, monkeypatch):
    values=setup_submission(platform, monkeypatch)
    monkeypatch.setattr(review_pilot,'SessionLocal',values[1])
    return values


def confirmed(values, draft=False, feedback='Teacher explanation'):
    client,_,teacher,_,sid,_,assignment,_=values
    criteria=[{'question_id':q['id'],'criterion_id':c['criterion_id'],'points':0,'comment':'Explain units carefully.'} for q in assignment['questions'] for c in q['criteria']]
    response=client.post('/api/document-review/'+sid,headers=teacher,json={'criteria':criteria,'feedback':feedback,'draft':draft})
    assert response.status_code==201,response.text
    return response.json(),criteria


def card_body(review, assignment):
    q=assignment['questions'][0]
    return {'review_id':review['id'],'question_id':q['id'],'criterion_id':q['criteria'][0]['criterion_id'],'title':'Units matter','rule':'State the units before substituting numbers.','kind':'reference','evidence':{'page_number':1,'observation':'Teacher checked the original formula and missing units.'}}


def test_cards_require_confirmed_teacher_decisions_and_keep_immutable_provenance(pilot):
    client,factory,teacher,student,sid,_,assignment,_=pilot
    draft,_=confirmed(pilot,True)
    path=f'/api/review-pilot/submissions/{sid}/cards'
    assert client.post(path,headers=teacher,json=card_body(draft,assignment)).status_code==409
    review,criteria=confirmed(pilot)
    body=card_body(review,assignment)
    saved=client.post(path,headers=teacher,json=body);assert saved.status_code==201,saved.text
    card=saved.json();assert card['kind']=='reference' and card['points']==0 and card['feedback']=='Explain units carefully.'
    assert card['source_hash'] and card['evidence_kind']=='teacher_observation'
    assert client.post(path,headers=teacher,json=body).json()['id']==card['id']
    query={'question_id':body['question_id'],'criterion_id':body['criterion_id']}
    listing=client.get(path,headers=teacher,params=query)
    assert listing.headers['cache-control']=='private, no-store' and listing.json()['items'][0]['id']==card['id']
    # Reusing records a new observed basis, and never copies a score or publishes.
    criteria[0].update(points=None,card_use={'card_id':card['id'],'evidence':{'page_number':2,'observation':'A separately observed omission on the new page.'}})
    result=client.post('/api/document-review/'+sid,headers=teacher,json={'criteria':criteria,'draft':True})
    assert result.status_code==201 and result.json()['criteria'][0]['points'] is None
    assert result.json()['criteria'][0]['card_use']['evidence']['page_number']==2
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ReviewDecisionCard))==1
        assert db.scalar(select(func.count()).select_from(AcademicGrade))==0
        assert db.get(ReviewDecisionCard,card['id']).snapshot['evidence']['page_number']==1
    # Source bounds, unknown rubric identity and malformed observations fail closed.
    for evidence in ({'page_number':0,'observation':'x'},{'page_number':4,'observation':'x'},{'page_number':True,'observation':'x'},{'page_number':1,'observation':'  '}):
        assert client.post(path,headers=teacher,json={**body,'evidence':evidence}).status_code==422
    assert client.post(path,headers=teacher,json={**body,'question_id':'unknown'}).status_code==422


def test_private_pilot_endpoints_reject_students_unauthenticated_and_other_teachers(pilot, platform):
    client,_,teacher,student,sid,_,assignment,_=pilot
    outsider=identity(client,platform[2], 'outsider-pilot@example.test')
    create_course(client,outsider,code='OUTSIDE')
    paths=[f'/api/review-pilot/submissions/{sid}/pages',f'/api/review-pilot/submissions/{sid}/cards?question_id=q1&criterion_id=q1-overall',f'/api/review-pilot/assignments/{assignment["id"]}/question-queue',f'/api/review-pilot/assignments/{assignment["id"]}/grades.csv']
    for path in paths:
        assert client.get(path).status_code==401
        for denied in (student,outsider):assert client.get(path,headers=denied).status_code==403
    review,_=confirmed(pilot);body=card_body(review,assignment)
    for denied in (student,outsider):
        assert client.post(f'/api/review-pilot/submissions/{sid}/cards',headers=denied,json=body).status_code==403
        assert client.post(f'/api/review-pilot/submissions/{sid}/pages',headers=denied,json={'question_id':'q1','pages':[1]}).status_code==403


def test_changed_rubric_and_cross_course_cards_cannot_be_applied(pilot):
    client,factory,teacher,_,sid,_,assignment,_=pilot
    review,criteria=confirmed(pilot);body=card_body(review,assignment)
    card=client.post(f'/api/review-pilot/submissions/{sid}/cards',headers=teacher,json=body).json()
    with factory() as db:
        row=db.get(AcademicAssignment,assignment['id']);questions=deepcopy(row.questions);questions[0]['criteria'][0]['description']='A different scientific rule';row.questions=questions;db.commit()
    path=f'/api/review-pilot/submissions/{sid}/cards'
    assert client.get(path,headers=teacher,params={'question_id':'q1','criterion_id':body['criterion_id']}).json()['items']==[]
    criteria[0]['card_use']={'card_id':card['id'],'evidence':{'page_number':1,'observation':'New observation'}}
    assert client.post('/api/document-review/'+sid,headers=teacher,json={'criteria':criteria,'draft':True}).status_code==409
    # A teacher owning both courses still cannot silently transfer course standards.
    other=create_course(client,teacher,code='OTHER')
    with factory() as db:
        row=db.get(AcademicAssignment,assignment['id']);row.offering_id=other['offering_id'];db.commit()
    assert client.post('/api/document-review/'+sid,headers=teacher,json={'criteria':criteria,'draft':True}).status_code==404


def test_question_pages_validate_bounds_versions_and_compare_and_swap(pilot):
    client,factory,teacher,_,sid,_,assignment,_=pilot
    path=f'/api/review-pilot/submissions/{sid}/pages'
    assert client.get(path,headers=teacher).json()=={'page_count':3,'items':[],'suggestions':[]}
    for pages in ([0],[4],[1,1],[1.5],[True],['1']):
        assert client.post(path,headers=teacher,json={'question_id':'q1','pages':pages}).status_code==422
    first=client.post(path,headers=teacher,json={'question_id':'q1','pages':[3,1]})
    assert first.status_code==201 and first.json()['pages']==[1,3]
    assert client.post(path,headers=teacher,json={'question_id':'q1','pages':[2]}).status_code==409
    with factory() as db:
        row=db.get(AcademicAssignment,assignment['id']);questions=deepcopy(row.questions);questions[0]['statement']='Changed question';row.questions=questions;db.commit()
    stale=client.get(path,headers=teacher).json()['items'][0];assert stale['stale'] and stale['pages']==[]
    updated=client.post(path,headers=teacher,json={'question_id':'q1','pages':[2],'expected_mapping_id':first.json()['id']})
    assert updated.status_code==201 and not updated.json()['stale']
    cleared=client.post(path,headers=teacher,json={'question_id':'q1','pages':[],'expected_mapping_id':updated.json()['id']})
    assert cleared.status_code==201
    with factory() as db:assert db.scalar(select(func.count()).select_from(QuestionPageMap))==3


def test_queue_uses_latest_attempt_and_never_invents_pages(pilot):
    client,factory,teacher,_,sid,_,assignment,_=pilot
    path=f'/api/review-pilot/assignments/{assignment["id"]}/question-queue'
    assert client.get(path,headers=teacher,params={'question_id':'missing'}).status_code==422
    original=client.get(path,headers=teacher,params={'question_id':'q1'}).json()
    assert original['items'][0]['id']==sid and original['items'][0]['mapping'] is None
    with factory() as db:
        old=db.get(AcademicSubmission,sid)
        new=AcademicSubmission(assignment_id=old.assignment_id,student_id=old.student_id,student_name=old.student_name,file_path='synthetic-new.pdf',file_name='synthetic-new.pdf',file_type='pdf',created_at=now_utc()+timedelta(seconds=1));db.add(new);db.commit();newid=new.id
    items=client.get(path,headers=teacher,params={'question_id':'q1'}).json()['items']
    assert len(items)==1 and items[0]['id']==newid and items[0]['mapping'] is None


def test_csv_exports_only_published_frozen_feedback_and_escapes_formula_cells(pilot):
    client,factory,teacher,_,sid,_,assignment,_=pilot
    path=f'/api/review-pilot/assignments/{assignment["id"]}/grades.csv'
    draft,_=confirmed(pilot,True)
    assert len(list(csv.reader(io.StringIO(client.get(path,headers=teacher).text.lstrip('\ufeff')))))==1
    review,_=confirmed(pilot,feedback='=untrusted student-facing text')
    with factory() as db:
        grade=AcademicGrade(assignment_id=assignment['id'],submission_id=sid,points=0,maximum_score=10,published=True,published_at=now_utc());db.add(grade);db.flush();db.add(PublishedDocumentReview(grade_id=grade.id,review_id=review['id']));db.commit()
    confirmed(pilot,True,feedback='A newer draft must stay private')
    result=client.get(path,headers=teacher);rows=list(csv.DictReader(io.StringIO(result.text.lstrip('\ufeff'))))
    assert len(rows)==1 and rows[0]['points']=='0.0' and rows[0]['review_id']==review['id']
    assert rows[0]['feedback']=="'=untrusted student-facing text"
    assert result.headers['cache-control']=='private, no-store'
    # Internal reuse provenance stays teacher-only even in a published review.
    from document_review import published_feedback
    with factory() as db:
        source=db.get(DocumentReview,review['id']);scores=deepcopy(source.criteria);scores[0]['card_use']={'card_id':'private-card','evidence':{'page_number':1,'observation':'Internal review note'}};source.criteria=scores;db.commit()
        grade=db.scalar(select(AcademicGrade));public=published_feedback(db,grade)
        assert all('card_use' not in criterion for criterion in public['criteria'])
        assert db.get(DocumentReview,review['id']).criteria[0]['card_use']
    for value in ('=x','  +x','-x','@x','\tx','\rx','\nx'):assert review_pilot.safe_csv(value).startswith("'")


def test_upload_retry_returns_same_receipt_without_extra_jobs_even_after_deadline(pilot,monkeypatch):
    client,factory,teacher,student,sid,_,assignment,content=pilot
    with factory() as db:
        db.get(AcademicAssignment,assignment['id']).allow_resubmission=True;db.commit()
    calls=[];monkeypatch.setattr(__import__('document_processing'),'enqueue',lambda *args,**kwargs:calls.append(1))
    key=str(uuid4());path=f'/academic/assignments/{assignment["id"]}/submissions'
    def upload(data=content,request_id=key):return client.post(path,headers=student,data={'request_id':request_id},files={'file':('synthetic.pdf',data,'application/pdf')})
    first=upload();assert first.status_code==201,first.text
    with factory() as db:
        db.get(AcademicAssignment,assignment['id']).due_at=now_utc()-timedelta(seconds=1);db.commit()
    retry=upload();assert retry.status_code==201 and retry.json()==first.json() and calls==[1]
    assert upload(content+b'\n').status_code==409
    assert upload(request_id=str(uuid4())).status_code==409
    assert upload(request_id='bad').status_code==422
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SubmissionUploadReceipt))==1
        assert db.scalar(select(func.count()).select_from(AcademicSubmission))==2  # Original fixture + one new attempt.


def test_additive_pilot_migration_preserves_sources_and_is_repeatable(pilot):
    from migrations import apply_migrations
    from account_models import SchemaMigration
    client,factory,_,_,sid,*_=pilot;engine=factory.kw['bind']
    with engine.begin() as connection:
        for model in (SubmissionUploadReceipt,QuestionPageMap,ReviewDecisionCard):model.__table__.drop(connection)
        connection.execute(SchemaMigration.__table__.delete().where(SchemaMigration.version=='012_review_pilot'))
    apply_migrations(engine);apply_migrations(engine)
    with factory() as db:
        assert db.get(AcademicSubmission,sid).file_name=='synthetic.pdf'
        assert db.get(SchemaMigration,'012_review_pilot')

def test_simultaneous_page_edits_conflict_instead_of_overwriting(pilot):
    client,_,teacher,_,sid,*_=pilot
    path=f'/api/review-pilot/submissions/{sid}/pages'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda page:client.post(path,headers=teacher,json={'question_id':'q1','pages':[page]}),[1,2]))
    assert sorted(r.status_code for r in results)==[201,409]
    assert client.get(path,headers=teacher).json()['items'][0]['pages'] in ([1],[2])


def test_simultaneous_upload_retries_share_one_attempt(pilot, monkeypatch):
    client,factory,_,student,_,_,assignment,content=pilot
    with factory() as db:db.get(AcademicAssignment,assignment['id']).allow_resubmission=True;db.commit()
    calls=[];monkeypatch.setattr(__import__('document_processing'),'enqueue',lambda *args,**kwargs:calls.append(1))
    key=str(uuid4());path=f'/academic/assignments/{assignment["id"]}/submissions'
    def upload(_):return client.post(path,headers=student,data={'request_id':key},files={'file':('synthetic.pdf',content,'application/pdf')})
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(upload,range(2)))
    assert all(r.status_code==201 for r in results)
    assert results[0].json()['id']==results[1].json()['id'] and calls==[1]


def test_assisted_cards_match_the_exact_approved_rubric_version(assessed, monkeypatch):
    import document_processing
    values,path,_,rubric=assessed
    client,factory,teacher,_,sid,_,assignment,_=values
    monkeypatch.setattr(review_pilot,'SessionLocal',factory)
    assert client.post(path,headers=teacher,json={}).status_code==202
    assert document_processing.process_one()
    suggestion=client.get(path,headers=teacher).json()['items'][0]
    decisions=[{'question_id':c['question_id'],'criterion_id':c['criterion_id'],'points':0,'feedback':'Confirmed explanation','finding':'concern','action':'accepted'} for c in suggestion['result']['criteria']]
    saved=client.post(path+'/decisions',headers=teacher,json={'suggestion_id':suggestion['id'],'decisions':decisions})
    assert saved.status_code==201
    body=card_body({'id':saved.json()['review_id']},assignment)
    cardpath=f'/api/review-pilot/submissions/{sid}/cards'
    card=client.post(cardpath,headers=teacher,json=body);assert card.status_code==201,card.text
    query={'question_id':body['question_id'],'criterion_id':body['criterion_id'],'rubric_id':suggestion['rubric']['id']}
    assert client.get(cardpath,headers=teacher,params=query).json()['items'][0]['id']==card.json()['id']
    assert client.get(cardpath,headers=teacher,params={k:v for k,v in query.items() if k!='rubric_id'}).json()['items']==[]
    decisions[0]['card_use']={'card_id':card.json()['id'],'evidence':{'page_number':2,'observation':'New original evidence'}}
    result=client.post(path+'/decisions',headers=teacher,json={'suggestion_id':suggestion['id'],'decisions':decisions,'draft':True})
    assert result.status_code==201,result.text
    assert client.get(path,headers=teacher).json()['items'][0]['decisions'][0]['decisions'][0]['card_use']

def test_postgresql_upload_and_mapping_races_in_disposable_schema(platform, monkeypatch):
    import os
    from urllib.parse import urlsplit
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import persistence, accounts, courses, permissions, assignment_api, email_delivery, institutions, document_processing, analysis_api, document_review, assessment_api
    from persistence import Base, _normalize_database_url
    from migrations import apply_migrations
    url=os.getenv('FORMA_TEST_POSTGRESQL_URL')
    if not url:pytest.skip('Set a disposable loopback PostgreSQL URL to test multi-connection pilot races.')
    if urlsplit(url).hostname not in ('localhost','127.0.0.1','::1'):pytest.fail('Pilot race tests require a local disposable PostgreSQL server.')
    schema='forma_pilot_test_'+uuid4().hex;root=create_engine(_normalize_database_url(url));scoped=None
    try:
        with root.begin() as connection:connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        scoped=create_engine(_normalize_database_url(url),connect_args={'options':'-csearch_path='+schema})
        Base.metadata.create_all(scoped);apply_migrations(scoped);apply_migrations(scoped)
        factory=__import__('sqlalchemy.orm',fromlist=['sessionmaker']).sessionmaker(scoped,expire_on_commit=False)
        for module in (persistence,accounts,courses,permissions,academic_api,assignment_api,email_delivery,institutions,document_processing,analysis_api,document_review,assessment_api,review_pilot):
            monkeypatch.setattr(module,'SessionLocal',factory)
        values=setup_submission((platform[0],factory,platform[2]),monkeypatch)
        client,_,teacher,student,sid,_,assignment,content=values
        with factory() as db:db.get(AcademicAssignment,assignment['id']).allow_resubmission=True;db.commit()
        calls=[];monkeypatch.setattr(document_processing,'enqueue',lambda *args,**kwargs:calls.append(1))
        key=str(uuid4());path=f'/academic/assignments/{assignment["id"]}/submissions'
        def upload(_):return client.post(path,headers=student,data={'request_id':key},files={'file':('synthetic.pdf',content,'application/pdf')})
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(upload,range(2)))
        assert all(r.status_code==201 for r in results),[r.text for r in results]
        assert results[0].json()['id']==results[1].json()['id'] and calls==[1]
        def map_page(page):return client.post(f'/api/review-pilot/submissions/{sid}/pages',headers=teacher,json={'question_id':'q1','pages':[page]})
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(map_page,[1,2]))
        assert sorted(r.status_code for r in results)==[201,409]
    finally:
        if scoped:scoped.dispose()
        with root.begin() as connection:connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        root.dispose()
