"""Synthetic content profiles, whole-file evidence and private archive comparison. No paid calls."""
import copy
import hashlib
import json
from sqlalchemy import select, func
import pytest
from test_accounts_courses import platform, identity
from test_document_processing import setup_submission
import document_integrity as api
import assignment_comparison as comparison_api
import document_processing as processing
from services import document_integrity as engine
from services.ai_providers.engine import configuration
from services.similarity_vectors import visual_signal, text_features
from integrity_models import DocumentIntegrityReport
from processing_models import ProcessingJob, DocumentInterpretation
from document_models import SubmissionDocument
from persistence import AcademicSubmission, AcademicGrade
from budget_models import AIRequestCharge


def completion(config,schema,system,context,*args):
    source=context['source'][0]
    return {'done':True,'done_reason':'stop','message':{'content':json.dumps({'features':[{'concept':'newtonian mechanics','unit':source['unit'],'quote':source['text'][:30]}],'style_signals':[]})}}


def test_full_text_chunks_and_exact_evidence_checkpoint_reuse(monkeypatch):
    calls=[]
    def chat(*args):calls.append(args[3]['source'][0]);return completion(*args)
    monkeypatch.setattr('services.ai_providers.ollama.structured_completion',chat)
    structure={'pages':[{'number':1,'text':'alpha beta '*600},{'number':2,'text':'distinctive conclusion and reasoning'}]}
    checkpoints=[]
    result,usage=engine.evaluate(structure,'essay',configuration('ollama'),'synthetic',checkpoint=lambda chunks:checkpoints.extend(copy.deepcopy(chunks[len(checkpoints):])))
    assert result['status']=='completed' and result['units_analyzed']==2 and result['chunks_analyzed']>2
    assert ''.join(c['text'] for c in calls)==''.join(p['text'] for p in structure['pages'])
    assert all(len(c['text'].encode())<=engine.BATCH_BYTES for c in calls)
    again,_=engine.evaluate(structure,'essay',configuration('ollama'),'synthetic',checkpoints=checkpoints)
    assert again==result and len(calls)==len(checkpoints)
    with pytest.raises(ValueError):engine.validate_observations({'features':[{'concept':'invented','unit':1,'quote':'invented text that is not present'}],'style_signals':[]},[{'unit':1,'text':'actual text'}])


def test_scans_oversize_and_problem_sets_do_not_become_authorship_percentages(monkeypatch):
    monkeypatch.setattr('services.ai_providers.ollama.structured_completion',completion)
    for source,status in [({'pages':[{'number':1,'text':''}]},'no_readable_text'),({'pages':[{'number':1,'text':'x'*50000}]},'input_limit')]:
        result,usage=engine.evaluate(source,'essay',configuration('ollama'),'synthetic')
        assert result['status']==status and result['authorship_probability'] is None and not usage['ai_called']
    result,_=engine.evaluate({'pages':[{'number':1,'text':'F = mass times acceleration, unit Newton.'}]},'problem_set',configuration('ollama'),'synthetic')
    assert result['detector_status']=='not_applicable' and result['authorship_probability'] is None


def test_one_matching_page_is_not_a_whole_file_match_and_late_text_is_used():
    a={'ink':bytes([20,0]),'norm':20,'digest':'a','page':1}
    b={'ink':bytes([0,20]),'norm':20,'digest':'b','page':2}
    result=visual_signal([a],[a,b])
    assert result['score']==.5 and result['matched_units_candidate']==1
    assert 'distinctivetail' in text_features(('common words '*5000)+' distinctivetail endmarker','')


def test_private_jobs_get_no_compute_idempotency_worker_and_stale_receipts(platform,monkeypatch):
    client,factory,teacher,student,sid,structure,assignment,content=setup_submission(platform,monkeypatch)
    monkeypatch.setattr(api,'SessionLocal',factory)
    monkeypatch.setenv('FORMA_INTEGRITY_PROVIDER','ollama')
    monkeypatch.setattr('services.ai_providers.ollama.structured_completion',completion)
    path='/api/document-integrity/'+sid
    assert client.get(path,headers=teacher).json()['status']=='not_analyzed'
    assert client.get(path,headers=student).status_code==403
    assert client.post(path,headers=student,json={}).status_code==403
    outsider=identity(client,platform[2],'unrelated@example.test')
    assert client.get(path,headers=outsider).status_code==403
    with factory() as db:assert db.scalar(select(func.count()).select_from(ProcessingJob))==0
    first=client.post(path,headers=teacher,json={});assert first.status_code==202,first.text
    assert client.post(path,headers=teacher,json={}).json()['id']==first.json()['id']
    assert processing.process_one()
    body=client.get(path,headers=teacher).json()
    assert body['status']=='completed' and body['detector_status']=='not_applicable'
    assert body['authorship_probability'] is None and body['report']['features']
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(DocumentIntegrityReport))==1
        assert db.scalar(select(func.count()).select_from(DocumentInterpretation))==0
        assert db.scalar(select(func.count()).select_from(AcademicGrade))==0
        assert db.scalar(select(func.count()).select_from(AIRequestCharge))==0
        db.get(SubmissionDocument,sid).content_hash='a'*64;db.commit()
    assert client.get(path,headers=teacher).json()['status']=='stale'


def test_selected_archive_files_authorize_every_source_cache_and_preserve_grades(platform,monkeypatch):
    client,factory,teacher,student,sid,structure,assignment,content=setup_submission(platform,monkeypatch)
    monkeypatch.setattr(comparison_api,'SessionLocal',factory);monkeypatch.setattr(comparison_api,'read_blob',lambda _:content)
    with factory() as db:
        other=AcademicSubmission(assignment_id=assignment['id'],student_id='second-student',student_name='Second',file_name='second.pdf',file_type='pdf',file_path='second.pdf',extracted_text=structure['extracted_text'])
        db.add(other);db.flush();db.add(SubmissionDocument(submission_id=other.id,content_hash=hashlib.sha256(content).hexdigest(),structure=structure));db.commit();oid=other.id
    path='/api/assignment-comparison/files/compare';payload={'submission_ids':[sid,oid]}
    assert client.post(path,headers=student,json=payload).status_code==403
    response=client.post(path,headers=teacher,json=payload);assert response.status_code==201,response.text
    result=response.json();assert result['comparison_scope']=='selected_files' and not result['stale']
    assert result['pairs'][0]['metrics']['document']['score']==1
    assert client.post(path,headers=teacher,json=payload).json()['id']==result['id']
    assert client.post(path,headers=teacher,json={'submission_ids':[sid,sid]}).status_code==422
    assert client.post(path,headers=teacher,json={'submission_ids':[sid,'missing']} ).status_code==404
    assert client.get('/api/assignment-comparison/'+assignment['id'],headers=teacher).json()['status']=='missing'
    with factory() as db:assert db.scalar(select(func.count()).select_from(AcademicGrade))==0
