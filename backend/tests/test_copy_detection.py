"""Synthetic copy transformations and private, resumable archive coverage."""
import base64
import copy
import hashlib
import io
import json
import random
import pytest
import pymupdf
from PIL import Image,ImageDraw
from sqlalchemy import select,func
from services.structured_output import model_object
from services.assessment_errors import AssessmentValidationError
from services.document_fingerprints import profile,compare
from services.similarity_vectors import analyze,visual_signal,image_feature
from test_accounts_courses import platform,identity
from test_document_processing import setup_submission
from persistence import AcademicSubmission,AcademicAssignment,AcademicGrade
from document_models import SubmissionDocument
from comparison_models import AssignmentComparison
import assignment_comparison
import archive_comparison


@pytest.mark.parametrize('wrapper',['{}','```json\n{}\n```','\ufeff {}','<think>checking the schema</think>\n{}','Here is the requested JSON:\n{}'])
def test_structured_wrappers_preserve_observed_text_and_latex_without_another_request(wrapper):
    value={'sections':[{'observed_text':'Literal { braces } and NaN in the original.','latex':r'\frac{x}{2}'}]}
    assert model_object(wrapper.format(json.dumps(value)) if wrapper!='{}' else json.dumps(value))==value


@pytest.mark.parametrize('raw',['garbage','{"sections":[','{"x":1}{"x":2}','{"x":1,"x":2}','{"x":NaN}',"{'sections':[]}",'```json\n{"x":1}\n'])
def test_incomplete_ambiguous_or_changed_json_never_becomes_a_success(raw):
    with pytest.raises(AssessmentValidationError) as error: model_object(raw)
    assert error.value.reason=='document_output_invalid_json'


def test_fingerprints_find_reordered_passages_keep_exact_quotes_and_exclude_task_text():
    first='The measured acceleration increases steadily because the applied force remains constant while friction decreases during the second part of the experiment.'
    other='We repeated every measurement with a calibrated instrument and estimated the error using the observed spread rather than the instrument resolution alone.'
    a=profile(first+'\n\n'+other,pages=[{'number':1,'text':first},{'number':2,'text':other}])
    b=profile(other+'\n\n'+first.upper())
    result=compare(a,b)
    assert result['score']==1 and len(result['evidence'])>=2
    for evidence in result['evidence']:
        for source,key in ((a,'current'),(b,'candidate')):
            span=evidence[key];assert source['text'][span['start']:span['end']]==span['quote']
    excluded=compare(profile(first,first),profile(first,first))
    assert excluded['score'] is None and not excluded['evidence']
    shuffled=' '.join(reversed(first.split()))
    lexical=compare(profile(first),profile(shuffled))
    assert lexical['score']==0 and lexical['evidence']==[]


def drawing(seed):
    rng=random.Random(seed);image=Image.new('L',(700,850),'white');pen=ImageDraw.Draw(image)
    for i in range(80):
        x,y=rng.randrange(50,620),rng.randrange(70,770)
        pen.ellipse((x,y,x+rng.randrange(4,25),y+rng.randrange(4,25)),outline=0,width=2)
        pen.line((x,y,x+rng.randrange(-25,26),y+rng.randrange(-35,36)),fill=0,width=2)
    return image


def scanned(image):
    stream=io.BytesIO();image.save(stream,format='PNG')
    pdf=pymupdf.open();page=pdf.new_page(width=image.width,height=image.height);page.insert_image(page.rect,stream=stream.getvalue())
    content=pdf.tobytes();pdf.close();return content


def doc(id,content,text=''):
    return {'id':id,'student_id':id,'file_name':id+'.pdf','file_type':'pdf','content':base64.b64encode(content).decode(),'text':text,'pages':[{'number':1,'text':text}]}


def test_geometric_matching_finds_a_rotated_cropped_scan_but_not_an_unrelated_page():
    original=drawing(12)
    changed=original.crop((45,65,650,790)).rotate(12,expand=True,fillcolor='white')
    a={**image_feature(original),'page':1};b={**image_feature(changed),'page':3}
    result=visual_signal([a],[b])
    assert result['score']>.1 and result['evidence'][0]['inliers']>=12
    assert result['evidence'][0]['method']=='orb_ransac'
    assert result['evidence'][0]['candidate']['page']==3
    unrelated=visual_signal([a],[{**image_feature(drawing(97)),'page':1}])
    assert unrelated['score']<.1 and unrelated['evidence']==[]


def test_a_shared_raster_template_alone_does_not_raise_the_document_index():
    raw=scanned(drawing(4))
    result=analyze({'documents':[doc('a',raw),doc('b',raw)],'baselines':[{'content':base64.b64encode(raw).decode(),'file_type':'pdf'}]})
    metrics=result['pairs'][0]['metrics']
    assert metrics['document']['identical_file']  # Preserve the true byte fact.
    assert metrics['document']['score'] is None and metrics['visual']['evidence']==[]


def test_shared_template_graphics_are_removed_before_comparing_different_answers():
    base=Image.new('L',(700,850),'white');base.paste(drawing(3).crop((0,0,700,400)),(0,0))
    first=base.copy();second=base.copy()
    first.paste(drawing(41).crop((0,0,700,400)),(0,440));second.paste(drawing(72).crop((0,0,700,400)),(0,440))
    value=analyze({'documents':[doc('a',scanned(first)),doc('b',scanned(second))],
        'baselines':[{'content':base64.b64encode(scanned(base)).decode(),'file_type':'pdf'}]})
    visual=value['pairs'][0]['metrics']['visual']
    assert visual['common_keypoints_removed']>20
    assert visual['score']<.1 and visual['evidence']==[]


def test_archive_scan_covers_past_assignments_resumes_and_never_runs_on_get(platform,monkeypatch):
    client,factory,teacher,student,sid,structure,assignment,raw=setup_submission(platform,monkeypatch)
    monkeypatch.setattr(assignment_comparison,'read_blob',lambda _:raw)
    with factory() as db:
        current=db.get(AcademicAssignment,assignment['id'])
        previous=AcademicAssignment(offering_id=current.offering_id,family_id=current.family_id,title='Previous cohort task',assignment_type=current.assignment_type,
            description=current.description,maximum_score=current.maximum_score,questions=current.questions)
        db.add(previous);db.flush()
        sources=[]
        for i in range(3):
            row=AcademicSubmission(assignment_id=previous.id,student_id=f'old-student-{i}',student_name='Private old student',file_name=f'old-{i}.pdf',file_path=f'old-{i}.pdf',file_type='pdf',extracted_text=structure['extracted_text'])
            db.add(row);db.flush();db.add(SubmissionDocument(submission_id=row.id,content_hash=hashlib.sha256(raw).hexdigest(),structure=structure));sources.append(row.id)
        # The same author's earlier work is not a plagiarism candidate.
        own=db.get(AcademicSubmission,sid)
        db.add(AcademicSubmission(assignment_id=previous.id,student_id=own.student_id,student_name=own.student_name,file_name='own.pdf',file_path='own.pdf',file_type='pdf'))
        db.commit()
    path='/api/assignment-comparison/archive/'+sid
    assert client.get(path,headers=student).status_code==403
    outsider=identity(client,platform[2],'outside-archive-files@example.com')
    assert client.get(path,headers=outsider).status_code==403
    first=client.get(path,headers=teacher).json()
    assert first['status']=='missing' and first['total']==3
    assert client.post(path,headers=student,json={}).status_code==403
    calls=[];real=archive_comparison.run_local
    def compute(payload):calls.append(payload);return real(payload)
    monkeypatch.setattr(archive_comparison,'run_local',compute)
    partial=client.post(path,headers=teacher,json={'expected_corpus':first['corpus_key']})
    assert partial.status_code==201,partial.text
    assert partial.json()['checked']==1 and partial.json()['remaining']==2 and not partial.json()['coverage_complete']
    assert client.get(path,headers=teacher).json()['checked']==1 and len(calls)==1
    for _ in range(2): partial=client.post(path,headers=teacher,json={'expected_corpus':first['corpus_key']})
    data=partial.json()
    assert data['coverage_complete'] and data['compared']==3 and data['remaining']==0
    assert len(data['pairs'])==3 and 'Private old student' not in partial.text
    assert client.post(path,headers=teacher,json={}).json()['checked']==3 and len(calls)==3
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AcademicGrade))==0
        assert db.scalar(select(func.count()).select_from(AssignmentComparison))==3
        row=db.get(AcademicSubmission,sources[0]);row.file_name='changed.pdf';db.commit()
    refreshed=client.get(path,headers=teacher).json()
    assert refreshed['stale'] and refreshed['checked']==0 and refreshed['pairs']==[]
    assert client.post(path,headers=teacher,json={'expected_corpus':first['corpus_key']}).status_code==409


def test_unavailable_archive_file_is_not_zero_can_be_retried_and_reverse_pair_reuses_the_receipt(platform,monkeypatch):
    client,factory,teacher,student,sid,structure,assignment,raw=setup_submission(platform,monkeypatch)
    with factory() as db:
        row=AcademicSubmission(assignment_id=assignment['id'],student_id='other-author',student_name='Other',file_name='old.pdf',file_path='old.pdf',file_type='pdf',extracted_text=structure['extracted_text'])
        db.add(row);db.flush();db.add(SubmissionDocument(submission_id=row.id,content_hash=hashlib.sha256(raw).hexdigest(),structure=structure));db.commit();other=row.id
    def unavailable(key):
        if key=='old.pdf':raise FileNotFoundError('private key')
        return raw
    monkeypatch.setattr(assignment_comparison,'read_blob',unavailable)
    path='/api/assignment-comparison/archive/'+sid
    failed=client.post(path,headers=teacher,json={})
    assert failed.status_code==201,failed.text
    assert failed.json()['status']=='incomplete' and failed.json()['skipped'] and not failed.json()['pairs']
    monkeypatch.setattr(assignment_comparison,'read_blob',lambda _:raw)
    retried=client.post(path,headers=teacher,json={'retry_unavailable':True})
    assert retried.status_code==201 and retried.json()['coverage_complete'] and retried.json()['skipped']==[]
    monkeypatch.setattr(archive_comparison,'run_local',lambda *_:pytest.fail('The reversed pair must reuse its saved result'))
    reverse=client.post('/api/assignment-comparison/archive/'+other,headers=teacher,json={})
    assert reverse.status_code==201 and reverse.json()['coverage_complete']
    assert len(reverse.json()['pairs'])==1
