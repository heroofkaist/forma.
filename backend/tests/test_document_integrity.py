"""Synthetic content profiles, whole-file evidence and private archive comparison. No paid calls."""
import hashlib
from sqlalchemy import select, func
import pytest
from test_accounts_courses import platform, identity
from test_document_processing import setup_submission
import document_integrity as api
import assignment_comparison as comparison_api
import document_processing as processing
from services import document_integrity as engine
from services.similarity_vectors import visual_signal, text_features
from integrity_models import DocumentIntegrityReport
from processing_models import ProcessingJob, DocumentInterpretation
from document_models import SubmissionDocument
from persistence import AcademicSubmission, AcademicGrade
from budget_models import AIRequestCharge


def forbid_models(monkeypatch):
    def unexpected(*args, **kwargs): raise AssertionError('Local detector must never call a language model')
    monkeypatch.setattr('services.ai_providers.ollama.structured_completion', unexpected)
    monkeypatch.setattr('services.ai_providers.openrouter.OpenRouterProvider.complete', unexpected)


def test_local_detector_covers_late_pages_preserves_evidence_and_never_calls_models(monkeypatch):
    forbid_models(monkeypatch)
    text='The experiment measures force and acceleration under controlled conditions. '*60
    structure={'pages':[{'number':1,'text':text}, {'number':2,'text':'As an AI language model, I cannot perform this experiment.'}]}
    result,usage=engine.evaluate(structure,'essay')
    assert result['status']=='completed' and result['units_analyzed']==2
    assert not usage['ai_called'] and usage['cost_usd']=='0.00'
    assert result['provider']=='local' and result['authorship_probability'] is None
    assert result['metrics']['word_count']>500
    assert result['style_signals'][0]['code']=='model_disclosure'
    assert result['style_signals'][0]['unit']==2
    for signal in result['style_signals']:
        assert signal['quote'] in structure['pages'][signal['unit']-1]['text']
        assert signal['alternative_explanation']
    assert engine.evaluate(structure,'essay')[0]==result


def test_scans_oversize_and_problem_sets_do_not_become_authorship_percentages(monkeypatch):
    forbid_models(monkeypatch)
    for source,status in [({'pages':[{'number':1,'text':''}]},'no_readable_text'),({'pages':[{'number':1,'text':'x'*(engine.MAX_INPUT_BYTES+1)}]},'input_limit')]:
        result,usage=engine.evaluate(source,'essay')
        assert result['status']==status and result['authorship_probability'] is None and not usage['ai_called']
        assert result['units_analyzed']==0
    result,_=engine.evaluate({'pages':[{'number':1,'text':'F = mass times acceleration, unit Newton.'}]},'problem_set')
    assert result['detector_status']=='not_applicable' and result['authorship_probability'] is None


def test_polished_regular_non_native_text_is_not_an_ai_verdict_and_short_artifacts_are_visible():
    text='We measured force in this experiment. We calculated error in every measurement. '*35
    clean,_=engine.evaluate({'pages':[{'number':1,'text':text}]},'lab_report')
    assert clean['style_signals']==[] and clean['detector_status']=='advisory'
    short,_=engine.evaluate({'pages':[{'number':1,'text':'Example: <|im_start|>assistant'}]},'programming')
    assert short['detector_status']=='advisory' and short['style_signals'][0]['code']=='chat_markup'
    russian,_=engine.evaluate({'pages':[{'number':1,'text':'Я языковая модель, поэтому не могу провести эксперимент.'}]},'essay')
    assert russian['style_signals'][0]['code']=='model_disclosure'
    paragraph=' '.join('word'+str(i) for i in range(45))
    repeats,_=engine.evaluate({'pages':[{'number':1,'text':paragraph+'\n\n'+paragraph}]},'essay')
    assert repeats['style_signals'][0]['code']=='repeated_passage'
    changed,_=engine.evaluate({'pages':[{'number':1,'text':paragraph+'\n\n'+paragraph.replace('word20', 'word99')}]},'lab_report')
    assert changed['style_signals']==[]


def test_one_matching_page_is_not_a_whole_file_match_and_late_text_is_used():
    from PIL import Image, ImageDraw
    from services.similarity_vectors import image_feature
    first=Image.new('L',(300,400),'white');ImageDraw.Draw(first).rectangle((20,30,180,190),fill='black')
    second=Image.new('L',(300,400),'white');ImageDraw.Draw(second).ellipse((100,200,260,350),fill='black')
    a={**image_feature(first),'page':1};b={**image_feature(second),'page':2}
    result=visual_signal([a],[a,b])
    assert result['score']==.5 and result['matched_units_candidate']==1
    assert 'distinctivetail' in text_features(('common words '*5000)+' distinctivetail endmarker','')


@pytest.mark.parametrize('legacy_queued', [False, True])
def test_private_jobs_get_no_compute_idempotency_worker_and_stale_receipts(platform,monkeypatch,legacy_queued):
    client,factory,teacher,student,sid,structure,assignment,content=setup_submission(platform,monkeypatch)
    monkeypatch.setattr(api,'SessionLocal',factory)
    monkeypatch.setenv('FORMA_INTEGRITY_PROVIDER','openrouter')
    monkeypatch.setenv('FORMA_AI_PAID_ENABLED','false')
    forbid_models(monkeypatch)
    path='/api/document-integrity/'+sid
    assert client.get(path,headers=teacher).json()['status']=='not_analyzed'
    assert client.get(path,headers=student).status_code==403
    assert client.post(path,headers=student,json={}).status_code==403
    outsider=identity(client,platform[2],'unrelated@example.test')
    assert client.get(path,headers=outsider).status_code==403
    with factory() as db:assert db.scalar(select(func.count()).select_from(ProcessingJob))==0
    first=client.post(path,headers=teacher,json={});assert first.status_code==202,first.text
    assert client.post(path,headers=teacher,json={}).json()['id']==first.json()['id']
    if legacy_queued:
        with factory() as db:
            job=db.get(ProcessingJob,first.json()['id'])
            job.context={**job.context,'ai':{'name':'openrouter','model':'qwen/legacy','version':'qwen-content-profile-v1','options':{}}}
            job.prompt_version='qwen-content-profile-v1';db.commit()
    assert processing.process_one()
    body=client.get(path,headers=teacher).json()
    assert body['status']=='completed' and body['detector_status']=='not_applicable'
    assert body['authorship_probability'] is None and body['report']['metrics']['word_count']>0
    assert body['report']['provider']=='local' and first.json()['maximum_cost_usd']=='0.00'
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
