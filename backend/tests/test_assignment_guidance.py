"""Teacher task context, criterion grouping and shared-cohort archive isolation. No inference."""
import copy
import hashlib
import json
from sqlalchemy import select
from test_accounts_courses import platform, identity, create_course
from test_document_processing import setup_submission
from persistence import AcademicSubmission, AcademicAssignment, CourseOffering, OriginalityReport, OriginalityAnalysis, AcademicGrade
from institution_models import CourseInstitution, InstitutionMembership, AccountRole
from document_models import SubmissionDocument
from course_archive_models import OriginalityCorpusSnapshot
from services.assignment_context import answer_groups, compact_context
from services.ai_providers.engine import configuration, DocumentRequest
from services.ai_providers.qwen import interpret_pages
from services.document_understanding import validate_result
import academic_api
import course_archive

TEXT='The heat engine transfers energy between two reservoirs and its efficiency depends on the temperatures and irreversible losses.'

def test_grouping_distinguishes_whole_work_problem_criteria_and_subcriteria():
    criteria=[{'criterion_id':f'c{i}','description':f'Задача {i}: решение и обоснование','maximum_points':5} for i in range(1,5)]
    questions=[{'id':'q1','title':'Midterm','maximum_points':20,'criteria':criteria}]
    assert len(answer_groups(questions,'problem_set'))==4
    assert all(len(g['criterion_ids'])==1 and g['question_id']=='q1' for g in answer_groups(questions,'problem_set'))
    assert len(answer_groups(questions,'lab_report'))==4
    for c in questions[0]['criteria']: c['description']=c['description'].replace('Задача ', '').split(':')[0]+' задача'
    assert [g['title'] for g in answer_groups(questions,'lab_report')]==['Задача 1','Задача 2','Задача 3','Задача 4']
    questions[0]['criteria']=[{'criterion_id':f'c{i}','description':title,'maximum_points':5} for i,title in enumerate(['Метод решения','Вычисления','Единицы измерения','Обоснование'])]
    assert len(answer_groups(questions,'problem_set'))==1
    explicit=[{**questions[0],'id':f'q{i}','title':f'Problem {i}'} for i in range(4)]
    assert len(answer_groups(explicit,'problem_set'))==4
    packed=compact_context({'instructions':'long condition '*4000,'files':[],'answer_groups':answer_groups(questions,'essay')})
    assert packed['context_shortened'] and packed['answer_groups'][0]['criterion_ids']==['c0','c1','c2','c3']
    fractional=academic_api.QuestionPayload(title='Task',maximum_points=.3,criteria=[
        academic_api.CriterionPayload(description='Method',maximum_points=.1),academic_api.CriterionPayload(description='Units',maximum_points=.2)])
    assert academic_api._normalize_questions([fractional],.3)[0]['maximum_points']==.3


def test_model_receives_task_sheet_rubric_and_preserves_known_association():
    questions=[{'id':'q1','title':'Problem 1','statement':'Find force','criteria':[{'criterion_id':'method','description':'Explain Newton law','maximum_points':5}]}]
    task={'instructions':'Use SI units','answer_groups':answer_groups(questions,'problem_set'), 'files':[{'id':'brief','name':'Task.pdf','text':'Mass is 2 kg and acceleration is 3 m/s2.','pages':1}]}
    structure={'pages':[{'number':1,'unit':'document','text':'F = ma = 6 N'}]}
    seen=[]
    def chat(images,context,timeout):
        assert not images;seen.append(context)
        return {'done':True,'done_reason':'stop','message':{'content':json.dumps({'sections':[{'page_number':1,'question_id':'q1','criterion_ids':['method'],'kind':'answer','observed_text':'F = ma = 6 N','evidence_kind':'embedded_text','readability':'readable'}]})}}
    request=DocumentRequest(b'', 'docx', structure, questions, 'problem_set', configuration('ollama'), assignment_context=task)
    result,_=interpret_pages(request,chat)
    assert seen[0]['teacher_assignment']['files'][0]['text'].startswith('Mass is 2 kg')
    assert seen[0]['teacher_assignment']['answer_groups'][0]['criteria'][0]['maximum_points']==5
    assert result['sections'][0]['criterion_ids']==['method']
    invalid=copy.deepcopy(result);invalid['sections'][0]['criterion_ids']=['foreign']
    import pytest
    with pytest.raises(ValueError):validate_result(invalid,structure,questions)


def test_question_batches_use_own_answer_and_reuse_completed_paid_batches(monkeypatch):
    from services.assessment import evaluate
    calls=[];checkpoints=[]
    rubric={'category':'problem_set','instructions':'Solve two independent problems.','reference_material':'','criteria':[
        {'question_id':f'q{i}','criterion_id':f'c{i}','description':'Show correct reasoning','maximum_points':5} for i in (1,2)]}
    source={'sections':[{'id':f's{i}','page_number':i,'question_id':f'q{i}','transcription':f'Observed answer number {i}.','readability':'readable'} for i in (1,2)]}
    def completion(config,schema,system,context,*args,**kwargs):
        calls.append(context);c=context['rubric']['criteria'][0];s=context['source']['sections'][0]
        assert len(context['source']['sections'])==1 and s['question_id']==c['question_id']
        value={**{k:c[k] for k in ('question_id','criterion_id')},'proposed_score':4,'rationale':'Observed reasoning','interpretation':'Model reasoning',
            'evidence':[{'section_id':s['id'],'page_number':s['page_number'],'quote':s['transcription']}], 'finding':'strength','suggested_improvement':'','missing_evidence':[],'uncertainty':[],'verification_status':'needs_review'}
        return {'message':{'content':json.dumps({'criteria':[value]})}}
    monkeypatch.setattr('services.ai_providers.ollama.structured_completion',completion)
    snapshot={'rubric':rubric,'source':source,'source_limitations':{},'title':'Two tasks'}
    first,_=evaluate(snapshot,configuration('ollama'),checkpoint=lambda data:checkpoints.extend(copy.deepcopy(data[len(checkpoints):])))
    again,_=evaluate(snapshot,configuration('ollama'),checkpoints=checkpoints)
    assert first==again and len(calls)==2 and len(checkpoints)==2
    from services.assessment import validate_assessment
    import pytest
    wrong=copy.deepcopy(first);wrong['criteria'][0]['evidence'][0]={'section_id':'s2','page_number':2,'quote':source['sections'][1]['transcription']}
    with pytest.raises(ValueError,match='different assignment question'):validate_assessment(wrong,rubric,source)


def test_archive_joins_teachers_and_years_refreshes_old_reports_but_never_opens_grades(platform,monkeypatch):
    import assignment_comparison
    client,factory,teacher,student,sid,structure,assignment,content=setup_submission(platform,monkeypatch)
    monkeypatch.setattr(course_archive,'read_blob',lambda _:content)
    monkeypatch.setattr(assignment_comparison,'SessionLocal',factory)
    monkeypatch.setattr(assignment_comparison,'read_blob',lambda _:content)
    with factory() as db:
        current=db.get(AcademicSubmission,sid);current.extracted_text=TEXT
        academic_api._compare_submission(db,current);db.commit()
        assert db.get(OriginalityAnalysis,sid).status=='no_sources'
        own_offering=db.get(CourseOffering,assignment['offering_id']);own_cid=own_offering.course_id
        institution=db.get(CourseInstitution,own_cid).institution_id
    other=identity(client,platform[2],'second-teacher@example.test')
    account=client.get('/api/auth/me',headers=other).json()['account_id']
    with factory() as db:
        db.get(AccountRole,account).role='teacher';db.add(InstitutionMembership(account_id=account,institution_id=institution,role='teacher'));db.commit()
    created=client.post('/api/courses',headers=other,json={'institution_id':institution,'title':'General Lab Physics I','code':'SCI101','subject':'Physics','academic_year':'2025','term':'Fall'})
    assert created.status_code==201,created.text
    past=created.json()
    task=client.post('/academic/assignments',headers=other,json={'offering_id':past['offering_id'],'title':'Past heat engine','maximum_score':10,'assignment_type':'lab_report'}).json()
    with factory() as db:
        source=AcademicSubmission(assignment_id=task['id'],student_id='previous-student',student_name='Private other student',file_name='Past.pdf',file_type='pdf',file_path='past.pdf',extracted_text=TEXT)
        db.add(source);db.flush();old_id=source.id
        db.add(SubmissionDocument(submission_id=old_id,content_hash=hashlib.sha256(content).hexdigest(),structure=structure));db.commit()
    result=client.get('/academic/submissions/'+sid+'/originality',headers=teacher)
    assert result.status_code==200,result.text
    assert result.json()['analysis']['match_ratio']==1 and result.json()['analysis']['candidate_count']==1
    report_id=result.json()['items'][0]['id']
    assert result.json()['items'][0]['candidate_student_id'] is None
    assert client.get('/academic/submissions/'+sid+'/originality',headers=teacher).json()['items'][0]['id']==report_id
    archive=client.get('/api/course-archive/search',params={'course_id':own_cid},headers=teacher)
    assert archive.status_code==200,archive.text
    archived=next(i for i in archive.json()['items'] if i['submission_id']==old_id)
    assert archived['student_name']=='Архивная работа' and not archived['can_review'] and not archived['student_id']
    readonly=client.get('/api/course-archive/files/'+old_id,headers=teacher)
    assert readonly.status_code==200 and 'reviews' not in readonly.json() and 'published_grade' not in readonly.json()
    assert client.get('/api/document-review/'+old_id,headers=teacher).status_code==403
    assert client.get('/api/course-archive/files/'+old_id+'/pages/1',headers=teacher).status_code==200
    assert client.get('/api/course-archive/files/'+old_id+'/file',headers=teacher).content==content
    assert client.get('/api/course-archive/search',headers=student).status_code==403
    for headers in (student,identity(client,platform[2],'outside@example.test')):
        assert client.get('/api/course-archive/files/'+old_id,headers=headers).status_code==403
    compared=client.post('/api/assignment-comparison/files/compare',headers=teacher,json={'submission_ids':[sid,old_id]})
    assert compared.status_code==201,compared.text
    assert all(d['student_id'].startswith('archive-') for d in compared.json()['documents'])
    with factory() as db:
        assert db.scalar(select(AcademicGrade)) is None
        assert db.get(OriginalityCorpusSnapshot,sid).report_ids==[report_id]
        old_report=db.get(OriginalityReport,report_id);old_report.review_status='follow_up';old_report.teacher_notes='Retain historical teacher context.';db.commit()
    # Same public code in another institution is never a shared archive.
    outside=create_course(client,teacher,code='SCI101')
    assert client.post(f'/api/course-archive/{assignment["offering_id"]}/link',headers=teacher,json={'target_course_id':outside['course_id']}).status_code==403
    alias=client.post('/api/courses',headers=other,json={'institution_id':institution,'title':'Physics laboratory','code':'PH141','subject':'Physics','academic_year':'2024','term':'Spring'}).json()
    # Different catalogue codes can be linked deliberately, within the institution.
    linked=client.post(f'/api/course-archive/{assignment["offering_id"]}/link',headers=teacher,json={'target_course_id':alias['course_id']})
    assert linked.status_code==200,linked.text
    refreshed=client.get('/academic/submissions/'+sid+'/originality',headers=teacher).json()
    assert refreshed['analysis']['analysis_status']=='no_sources'
    with factory() as db:
        assert db.get(OriginalityReport,report_id).teacher_notes=='Retain historical teacher context.'
        assert db.get(OriginalityCorpusSnapshot,sid).report_ids==[]


def test_assessment_uses_existing_assignment_criteria_without_reentering_a_rubric(platform,monkeypatch):
    from processing_models import ProcessingJob
    from assessment_models import AssessmentRubric
    import document_processing
    import assessment_api
    client,factory,teacher,student,sid,structure,assignment,content=setup_submission(platform,monkeypatch)
    monkeypatch.setattr(assessment_api,'SessionLocal',factory)
    with factory() as db:
        row=db.get(AcademicAssignment,assignment['id']);row.description='Solve each question and justify the physical law.'
        row.questions=[{**q,'criteria':[{**c,'description':'Explain the method and show correct calculations'} for c in q['criteria']]} for q in row.questions];db.commit()
    assert client.post('/api/document-analysis/'+sid,headers=teacher,json={}).status_code==202
    assert document_processing.process_one()
    response=client.post('/api/assessment/'+sid,headers=teacher,json={})
    assert response.status_code==202,response.text
    with factory() as db:
        job=db.get(ProcessingJob,response.json()['id']);rubric=db.scalar(select(AssessmentRubric))
        assert rubric.spec['instructions'].startswith('Solve each question')
        assert {c['question_id'] for c in rubric.spec['criteria']}=={'q1','q2'}
        assert all(c['maximum_points']==5 for c in rubric.spec['criteria'])
        assert job.context['assessment']['assignment_context']['instructions'].startswith('Solve each question')


def test_archive_catalogue_migration_and_aliases_on_postgresql():
    import os
    import pytest
    from sqlalchemy.orm import sessionmaker
    from test_academic_seed import _isolated_connection
    from migrations import apply_migrations
    from persistence import init_db, AcademicCourse
    from institution_models import Institution
    from course_archive_models import CourseArchiveLink
    url=os.getenv('FORMA_TEST_POSTGRESQL_URL')
    if not url:pytest.skip('A dedicated disposable PostgreSQL server is required.')
    with _isolated_connection(url) as connection:
        factory=sessionmaker(bind=connection,expire_on_commit=False)
        init_db(connection,factory);apply_migrations(connection);apply_migrations(connection)
        with factory() as db:
            db.add_all([Institution(id='school',name='School'),Institution(id='other-school',name='Other')]);db.flush()
            for cid,code,institution in [('a','PH-101','school'),('b','PH101','school'),('c','PH 101','other-school')]:
                db.add(AcademicCourse(id=cid,code=code,name='Physics',instructor='Teacher',department='Science'));db.flush()
                db.add(CourseInstitution(course_id=cid,institution_id=institution))
            db.flush()
            assert set(course_archive.course_ids(db,'a'))=={'a','b'}
            assert course_archive.course_ids(db,'c')==['c']
            db.add(CourseArchiveLink(course_id='b',archive_key='separate'));db.flush()
            assert course_archive.course_ids(db,'a')==['a']
