from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import hashlib
import pytest
import pymupdf
from sqlalchemy import select
from test_accounts_courses import platform, identity, create_course
import document_processing as processing
import analysis_api
from processing_models import ProcessingJob, DocumentInterpretation, InterpretationCorrection
from document_models import SubmissionDocument
from persistence import AcademicSubmission, AcademicAssignment, now_utc
from services.document_ingestion import ingest
from services.document_understanding import deterministic_interpretation, validate_result


def setup_submission(platform, monkeypatch, pages=None):
    client, factory, sent = platform
    monkeypatch.setattr(analysis_api,'SessionLocal',factory)
    monkeypatch.setattr(__import__('document_review'),'SessionLocal',factory)
    teacher=identity(client,sent,'teacher@example.com'); student=identity(client,sent,'student@example.com')
    course=create_course(client,teacher)
    client.post('/api/enrollment/join',headers=student,json={'class_code':course['class_code']})
    assignment=client.post('/academic/assignments',headers=teacher,json={'offering_id':course['offering_id'],'title':'Math work','assignment_type':'problem_set','maximum_score':10,'questions':[{'id':'q1','title':'Question 1','maximum_points':5,'statement':'Calculate force.'},{'id':'q2','title':'Question 2','maximum_points':5,'statement':'Explain the method.'}]}).json()
    doc=pymupdf.open()
    for text in pages or ['Question 1\nF = ma','continued solution','Question 2\nExplanation']:
        page=doc.new_page()
        if text: page.insert_text((48,72),text)
    content=doc.tobytes();doc.close()
    structure=ingest(content,'synthetic.pdf')
    student_id=client.get('/api/auth/me',headers=student).json()['account_id']
    with factory() as db:
        row=AcademicSubmission(assignment_id=assignment['id'],student_id=student_id,student_name='Synthetic student',file_path='synthetic.pdf',file_name='synthetic.pdf',file_type='pdf');db.add(row);db.flush()
        db.add(SubmissionDocument(submission_id=row.id,content_hash=hashlib.sha256(content).hexdigest(),structure=structure));db.commit();submission_id=row.id
    monkeypatch.setattr(processing,'read_blob',lambda _:content)
    return client,factory,teacher,student,submission_id,structure,assignment,content


def test_queue_claim_idempotency_and_full_document_without_cropping(platform,monkeypatch):
    client,factory,teacher,student,sid,structure,assignment,content=setup_submission(platform,monkeypatch)
    path='/api/document-analysis/'+sid
    assert client.post(path,headers=student,json={}).status_code==403
    first=client.post(path,headers=teacher,json={});second=client.post(path,headers=teacher,json={})
    assert first.status_code==202 and first.json()['id']==second.json()['id']
    assert processing.process_one()
    assert not processing.process_one()
    result=client.get(path,headers=teacher).json()['items'][0]
    assert result['original']['requires_human_review']
    association=result['original']['question_associations'][0]
    selected={section['id']:section for section in result['original']['sections']}
    assert {selected[key]['page_number'] for key in association['section_ids']}=={1,2}
    assert client.get(path,headers=student).status_code==403
    assert client.get(path+'/status',headers=student).json()['jobs'][0]['status']=='needs_review'
    assert any('not configured' in warning for warning in result['original']['warnings'])
    assert client.get('/academic/student/grades',headers=student).json()['items']==[]


def test_atomic_claim_expired_lease_and_bounded_retries(platform,monkeypatch):
    client,factory,teacher,student,sid,*_=setup_submission(platform,monkeypatch)
    client.post('/api/document-analysis/'+sid,headers=teacher,json={})
    with ThreadPoolExecutor(max_workers=2) as pool: claims=list(pool.map(lambda _:processing.claim(),range(2)))
    assert sum(value is not None for value in claims)==1
    with factory() as db:
        job=db.scalar(select(ProcessingJob)); old=job.lease_owner; job.lease_until=now_utc()-timedelta(seconds=1);db.commit()
    recovered=processing.claim();assert recovered and recovered[1]!=old
    with factory() as db:
        job=db.scalar(select(ProcessingJob));job.attempts=3;job.lease_until=now_utc()-timedelta(seconds=1);db.commit()
    assert processing.claim() is None
    with factory() as db: assert db.scalar(select(ProcessingJob)).status=='failed'


def test_model_response_evidence_validation_and_corrections_preserve_original(platform,monkeypatch):
    client,factory,teacher,student,sid,structure,assignment,*_=setup_submission(platform,monkeypatch)
    original=deterministic_interpretation(structure,assignment['questions'],'problem_set')
    monkeypatch.setattr(processing,'interpret_document',lambda *args, **kwargs:(original,{'ai_called':True,'input_tokens':100}))
    path='/api/document-analysis/'+sid
    client.post(path,headers=teacher,json={});assert processing.process_one()
    item=client.get(path,headers=teacher).json()['items'][0]
    corrected=__import__('copy').deepcopy(item['original']);corrected['sections'][0]['transcription']='Teacher corrected equation';corrected['sections'][0]['evidence_kind']='teacher_correction'
    body={'interpretation_id':item['id'],'result':corrected,'confirmed':True}
    assert client.post(path+'/corrections',headers=student,json=body).status_code==403
    assert client.post(path+'/corrections',headers=teacher,json=body).status_code==201
    latest=client.get(path,headers=teacher).json()['items'][0]
    assert latest['original']==original
    assert latest['corrections'][0]['result']['sections'][0]['transcription']=='Teacher corrected equation'
    assert client.get(path+'/status',headers=student).json()['jobs'][0]['status']=='completed'
    corrected['sections'][0]['page_number']=999
    assert client.post(path+'/corrections',headers=teacher,json={**body,'result':corrected}).status_code==422


def test_retry_temporary_provider_failure(platform,monkeypatch):
    client,factory,teacher,student,sid,*_=setup_submission(platform,monkeypatch)
    client.post('/api/document-analysis/'+sid,headers=teacher,json={})
    def fail(*args, **kwargs): raise TimeoutError('private content must never enter logs')
    monkeypatch.setattr(processing,'interpret_document',fail)
    for attempt in range(3):
        assert processing.process_one()
        with factory() as db:
            job=db.scalar(select(ProcessingJob));job.available_at=now_utc()-timedelta(seconds=1);db.commit()
    with factory() as db:
        job=db.scalar(select(ProcessingJob));assert job.status=='failed' and job.attempts==3 and 'private content' not in job.error


def test_unreadable_pages_missing_labels_and_invalid_model_evidence():
    structure={'pages':[{'number':1,'unit':'page','text':''},{'number':2,'unit':'page','text':'Unlabelled text'}],'warnings':[]}
    questions=[{'id':'q1','title':'Question 1'}]
    result=deterministic_interpretation(structure,questions,'problem_set')
    assert result['sections'][0]['readability']=='uncertain'
    assert result['question_associations'][0]['status']=='missing'
    result['sections'][0]['transcription']='Invented unreadable writing'
    with pytest.raises(ValueError):validate_result(result,structure,questions)
    result['sections'][0].update(evidence_kind='visual_page',transcription='F = ma')
    with pytest.raises(ValueError):validate_result(result,structure,questions,visual_pages=[])


def test_bounded_visual_gemini_request_and_schema_response(monkeypatch):
    import io
    import json
    from types import SimpleNamespace
    from PIL import Image, ImageDraw
    from services import document_understanding as understanding
    image=Image.new('RGB',(600,800),'white');ImageDraw.Draw(image).text((40,80),'Question 1: F = ma',fill='black');stream=io.BytesIO();image.save(stream,format='PNG')
    document=pymupdf.open()
    for _ in range(3):
        page=document.new_page();page.insert_image(page.rect,stream=stream.getvalue())
    content=document.tobytes();document.close()
    structure=ingest(content,'scan.pdf');calls=[]
    response={'document_type':'problem_set','sections':[{'id':'s1','page_number':1,'kind':'equation','transcription':'F = ma','question_id':'q1','readability':'uncertain','rationale':'Synthetic visual response','uncertainty_notes':['Handwriting needs confirmation.'],'evidence_kind':'visual_page'}],'question_associations':[{'question_id':'q1','section_ids':['s1'],'status':'proposed','reason':'Observed label.'}],'warnings':[],'requires_human_review':True}
    class FakeClient:
        def __init__(self,**kwargs):
            assert kwargs['http_options'].timeout==60000
            assert kwargs['http_options'].retry_options.attempts==1
            self.models=self
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def generate_content(self,**kwargs):
            calls.append(kwargs)
            assert kwargs['model']=='configured-synthetic-model'
            assert sum(not isinstance(part,str) for part in kwargs['contents'])==1
            return SimpleNamespace(text=json.dumps(response),usage_metadata=SimpleNamespace(prompt_token_count=100,candidates_token_count=50))
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-test-key')
    monkeypatch.setattr(understanding.genai,'Client',FakeClient)
    result,usage=understanding.gemini_interpret(content,'pdf',structure,[{'id':'q1','title':'Question 1'}],'problem_set','configured-synthetic-model',1)
    assert len(calls)==1 and usage['visual_pages']==1 and usage['output_tokens']==50
    assert any('budget' in warning for warning in result['warnings'])
    assert result['sections'][0]['readability']=='uncertain'


def test_identical_same_offering_document_uses_validated_cache(platform,monkeypatch):
    client,factory,teacher,student,sid,structure,assignment,content=setup_submission(platform,monkeypatch)
    calls=[]
    result=deterministic_interpretation(structure,assignment['questions'],'problem_set')
    def interpret(*args, **kwargs):calls.append(1);return result,{'ai_called':True,'visual_pages':0}
    monkeypatch.setattr(processing,'interpret_document',interpret)
    client.post('/api/document-analysis/'+sid,headers=teacher,json={});processing.process_one()
    with factory() as db:
        original=db.get(AcademicSubmission,sid)
        duplicate=AcademicSubmission(assignment_id=original.assignment_id,student_id=original.student_id,student_name=original.student_name,file_path=original.file_path,file_name=original.file_name,file_type=original.file_type);db.add(duplicate);db.flush()
        db.add(SubmissionDocument(submission_id=duplicate.id,content_hash=hashlib.sha256(content).hexdigest(),structure=structure));db.commit();second_id=duplicate.id
    client.post('/api/document-analysis/'+second_id,headers=teacher,json={});processing.process_one()
    assert len(calls)==1
    with factory() as db:
        job=db.scalar(select(ProcessingJob).where(ProcessingJob.submission_id==second_id))
        assert job.usage['cache_hit'] and job.status=='needs_review'


def test_reanalysis_versions_and_three_version_limit(platform,monkeypatch):
    client,factory,teacher,student,sid,*_=setup_submission(platform,monkeypatch)
    path='/api/document-analysis/'+sid
    for index in range(3):
        response=client.post(path,headers=teacher,json={'reanalyze':index>0});assert response.status_code==202;assert processing.process_one()
    assert len(client.get(path,headers=teacher).json()['items'])==3
    assert client.post(path,headers=teacher,json={'reanalyze':True}).status_code==429


def test_uploaded_task_sheet_requires_approval_and_informs_job(platform,monkeypatch):
    import assignment_briefs
    client,factory,teacher,student,sid,structure,assignment,*_=setup_submission(platform,monkeypatch)
    monkeypatch.setattr(assignment_briefs,'SessionLocal',factory)
    monkeypatch.setattr(assignment_briefs,'write_blob',lambda *args, **kwargs:None)
    paper=pymupdf.open();paper.new_page().insert_text((48,72),'Question 7: Explain forces.\nQuestion 8: Discuss uncertainty.');content=paper.tobytes();paper.close()
    path='/api/assignment-briefs/'+assignment['id']
    assert client.post(path,headers=student,files={'file':('task.pdf',content,'application/pdf')}).status_code==403
    response=client.post(path,headers=teacher,files={'file':('task.pdf',content,'application/pdf')})
    assert response.status_code==201,response.text
    proposed=response.json()['questions'];assert [question['id'] for question in proposed]==['brief-q7','brief-q8']
    assert client.post(path+'/approve',headers=teacher,json={'brief_id':response.json()['id'],'questions':proposed}).status_code==200
    queued=client.post('/api/document-analysis/'+sid,headers=teacher,json={})
    assert queued.status_code==202
    with factory() as db:
        job=db.get(ProcessingJob,queued.json()['id']);assert [q['id'] for q in job.context['questions']]==['q1','q2']
        assert job.context['assignment_context']['files'][0]['questions']==proposed
        assert db.get(AcademicAssignment,assignment['id']).questions[0]['id']=='q1'  # Rubric unchanged.
