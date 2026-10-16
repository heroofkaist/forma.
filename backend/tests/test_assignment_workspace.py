"""Synthetic roster integration and bounded local comparisons; no providers or grades."""
import base64
import hashlib
from datetime import timedelta
import json
from uuid import uuid4
import pytest
import pymupdf
from sqlalchemy import select, func
from test_accounts_courses import platform, identity
from test_document_processing import setup_submission
from persistence import AcademicSubmission, AcademicAssignment, CourseEnrollment, OriginalityAnalysis, AcademicGrade, now_utc
from account_models import EnrollmentState
from document_models import SubmissionDocument
from comparison_models import AssignmentComparison
import assignment_comparison as api
from services.similarity_vectors import analyze, VERSION


def document(id,text,kind='py',content=b'not executed',pages=None,student=None):
    return {'id':id,'student_id':student or id,'file_name':'synthetic.'+kind,'file_type':kind,'text':text,'pages':pages or [{'number':1,'text':text}], 'content':base64.b64encode(content).decode()}


def test_vector_reordering_formula_code_renaming_empty_and_same_author():
    one='alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi'
    two=' '.join(reversed(one.split()))
    result=analyze({'documents':[document('a',one,'txt'),document('b',two,'txt')]})
    assert result['version']==VERSION and result['pairs'][0]['metrics']['text']['score']>.3
    assert result['pairs'][0]['metrics']['visual']['score'] is None
    assert result['pairs'][0]['metrics']['formula']['score'] is None
    a='def solve(values):\n total = 0\n for x in values:\n  total += x * x\n return total\n'
    b=a.replace('solve','calculate').replace('values','numbers').replace('total','answer').replace(' x',' element')
    value=analyze({'documents':[document('a',a),document('b',b)]})['pairs'][0]['metrics']['code']
    assert value['status']=='completed' and value['score']>.8
    formulas=analyze({'documents':[document('a','F = m * a\ny = x + 2','pdf',pdf('F = m * a')),document('b','F=m*a\ny=x+2','pdf',pdf('F=m*a'))]})
    assert formulas['pairs'][0]['metrics']['formula']['score']==1
    empty=analyze({'documents':[document('a','','txt'),document('b','','txt')]})
    assert all(m['score'] is None for m in empty['pairs'][0]['metrics'].values())
    same=analyze({'documents':[document('a',one,student='same'),document('b',one,student='same')]})
    assert same['pairs']==[]
    excluded=analyze({'context':one,'documents':[document('a',one,'txt'),document('b',one,'txt')]})
    assert excluded['pairs'][0]['metrics']['text']['score'] is None
    with pytest.raises(ValueError):analyze({'documents':[document('a',one)]})


def pdf(text=''):
    doc=pymupdf.open();page=doc.new_page()
    if text:
        for i in range(12): page.insert_text((40,50+i*30),text+' '+str(i))
    content=doc.tobytes();doc.close();return content


def test_visual_receipt_identical_scanned_pages_and_blank_guard():
    # Raster-only input has no embedded text; visual matching still works.
    source=pymupdf.open(stream=pdf('Synthetic graph and calculations'),filetype='pdf')
    image=source[0].get_pixmap().tobytes('png');source.close()
    scan=pymupdf.open();page=scan.new_page();page.insert_image(page.rect,stream=image);raw=scan.tobytes();scan.close()
    value=analyze({'documents':[document('a','','pdf',raw),document('b','','pdf',raw)]})['pairs'][0]['metrics']
    assert value['text']['score'] is None
    assert value['visual']['score']==1 and value['visual']['evidence'][0]['current']['page']==1
    assert value['visual']['evidence'][0]['identical_thumbnail']
    blank=analyze({'documents':[document('a','','pdf',pdf()),document('b','','pdf',pdf())]})
    assert blank['pairs'][0]['metrics']['visual']['score'] is None


def test_worker_real_subprocess_and_failure_has_no_successful_zero(monkeypatch):
    value=api.run_local({'documents':[document('a','one two three four five six seven eight nine','txt'),document('b','nine eight seven six five four three two one','txt')]})
    assert value['version']==VERSION and len(value['pairs'])==1
    import subprocess
    monkeypatch.setattr(api.subprocess,'run',lambda *a,**k:(_ for _ in ()).throw(subprocess.TimeoutExpired('local',30)))
    with pytest.raises(Exception) as error: api.run_local({'documents':[]})
    assert error.value.status_code==422


def test_code_is_never_executed_and_visual_limits_fail_closed(tmp_path,monkeypatch):
    marker=tmp_path/'must-not-exist'
    code=f"__import__('pathlib').Path({str(marker)!r}).write_text('executed')\n"*10
    analyze({'documents':[document('a',code),document('b',code)]})
    assert not marker.exists()
    import services.similarity_vectors as vectors
    monkeypatch.setattr(vectors,'MAX_PAGES',1)
    with pytest.raises(ValueError):
        analyze({'documents':[document('a','','pdf',pdf()),document('b','','pdf',pdf())]})


def test_assignment_roster_identity_latest_attempts_and_receipt_states(platform,monkeypatch):
    client,factory,teacher,student,sid,_,assignment,content=setup_submission(platform,monkeypatch)
    with factory() as db:
        original=db.get(AcademicSubmission,sid)
        db.add(CourseEnrollment(offering_id=assignment['offering_id'],student_id='no-work',student_name='Synthetic waiting student'))
        suspended=CourseEnrollment(offering_id=assignment['offering_id'],student_id='suspended',student_name='Suspended');db.add(suspended);db.flush();db.add(EnrollmentState(enrollment_id=suspended.id,status='suspended'))
        repeat=AcademicSubmission(assignment_id=assignment['id'],student_id=original.student_id,student_name='old name',file_name='new.pdf',file_type='pdf',file_path='unused',created_at=now_utc()+timedelta(seconds=1));db.add(repeat);db.flush()
        db.add(OriginalityAnalysis(submission_id=repeat.id,status='failed',scope='family',eligible_token_count=0,candidate_count=0));db.commit();rid=repeat.id;student_id=original.student_id
    path='/api/assignment-submissions/'+assignment['id']
    response=client.get(path,headers=teacher);assert response.status_code==200,response.text
    assert response.headers['cache-control']=='private, no-store'
    data=response.json();assert data['course_name'] and data['maximum_score']==10 and data['due_at'] is None
    assert {s['student_id'] for s in data['students']}=={student_id,'no-work'}
    assert len(data['items'])==2 and data['items'][0]['id']==rid
    assert data['items'][0]['similarity']=={'analysis_status':'failed','match_ratio':None,'candidate_count':0,'eligible_token_count':0}
    assert data['items'][1]['similarity']['analysis_status']=='missing'
    assert client.get(path,headers=student).status_code==403
    outsider=identity(client,platform[2],'outsider@example.test');assert client.get(path,headers=outsider).status_code==403
    review=client.get('/api/document-review/'+sid,headers=teacher).json();assert review['student_id']==student_id


def test_saved_comparison_access_cache_stale_and_no_publication(platform,monkeypatch):
    client,factory,teacher,student,sid,structure,assignment,content=setup_submission(platform,monkeypatch)
    monkeypatch.setattr(api,'SessionLocal',factory);monkeypatch.setattr(api,'read_blob',lambda path:content)
    path='/api/assignment-comparison/'+assignment['id']
    assert client.get(path,headers=teacher).json()['status']=='missing'
    assert client.post(path,headers=teacher,json={}).status_code==422
    with factory() as db:
        db.get(AcademicSubmission,sid).extracted_text=structure['extracted_text']
        other=AcademicSubmission(assignment_id=assignment['id'],student_id='synthetic-other',student_name='Other student',file_name='other.pdf',file_type='pdf',file_path='other.pdf',extracted_text=structure['extracted_text']);db.add(other);db.flush()
        db.add(SubmissionDocument(submission_id=other.id,content_hash=hashlib.sha256(content).hexdigest(),structure=structure));db.commit();oid=other.id
    result=client.post(path,headers=teacher,json={});assert result.status_code==201,result.text
    body=result.json();assert body['status']=='completed' and not body['stale'] and len(body['pairs'])==1
    monkeypatch.setattr(api,'run_local',lambda *_:(_ for _ in ()).throw(AssertionError('cached/GET must not calculate')))
    assert client.get(path,headers=teacher).json()['id']==body['id']
    assert client.post(path,headers=teacher,json={}).json()['id']==body['id']
    for headers in [student,identity(client,platform[2],'not-authorized@example.test')]:
        assert client.get(path,headers=headers).status_code==403
        assert client.post(path,headers=headers,json={}).status_code==403
    with factory() as db:
        db.get(AcademicSubmission,oid).file_name='changed.pdf';db.commit()
        assert db.scalar(select(func.count()).select_from(AcademicGrade))==0
        assert db.scalar(select(func.count()).select_from(AssignmentComparison))==1
    assert client.get(path,headers=teacher).json()['stale']
    # A failed refresh cannot replace the old receipt with a successful zero.
    from fastapi import HTTPException
    monkeypatch.setattr(api,'run_local',lambda *_:(_ for _ in ()).throw(HTTPException(422,'Synthetic limit failure')))
    assert client.post(path,headers=teacher,json={}).status_code==422
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AssignmentComparison))==1
        from budget_models import AIRequestCharge
        from processing_models import ProcessingJob
        assert db.scalar(select(func.count()).select_from(AIRequestCharge))==0
        assert db.scalar(select(func.count()).select_from(ProcessingJob))==0
