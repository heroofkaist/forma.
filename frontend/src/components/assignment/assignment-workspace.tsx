"use client";
import Link from 'next/link';
import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {AssignmentTemplate} from '../assignment-template';
import {AssignmentBriefs} from '../assignment-briefs';
import {IntegritySignal} from './integrity-signal';
import {INTEGRITY_NOTE} from '../../lib/document-integrity';
import {ComparisonPanel} from './comparison-panel';
import {downloadAuthenticatedFile} from '../../lib/api';
import {platformRequest} from '../../lib/platform';
import {humanReviewLabel,aiProcessingLabel} from '../../lib/submission-status';
import {studentWorks,filterStudentWorks,textSimilarityLabel,fileMatchFor,comparisonUrl,type Comparison,type AssignmentWorkspace as Workspace,type WorkFilter,type AssignmentWork} from '../../lib/assignment-workspace';

function date(value:string|null){const d=value?new Date(value):null;return d&&Number.isFinite(d.getTime())?d.toLocaleString('ru-RU'):'Без срока';}
export function AssignmentRegister({data,comparison}:{data:Workspace;comparison?:Comparison|null}){
  const [query,setQuery]=useState(''),[filter,setFilter]=useState<WorkFilter>('all'),[downloadError,setDownloadError]=useState('');
  const rows=useMemo(()=>studentWorks(data),[data]),visible=filterStudentWorks(rows,query,filter);
  async function download(work:AssignmentWork){setDownloadError('');try{await downloadAuthenticatedFile(`/api/submission-files/${work.id}`,work.file_name);}catch{setDownloadError('Не удалось скачать оригинал. Работа и введённые фильтры сохранены.');}}
  return <section aria-labelledby="assignment-register-title"><div className="assignment-section-heading"><div><h2 id="assignment-register-title">Студенты и работы</h2><p>Последняя отправленная работа каждого студента. Предыдущие попытки доступны в списке.</p></div><span>{visible.length} из {rows.length}</span></div>
    <div className="assignment-register-tools"><label>Поиск<input type="search" value={query} placeholder="Имя, ID или имя файла" onChange={e=>setQuery(e.target.value)}/></label><label>Показать<select value={filter} onChange={e=>setFilter(e.target.value as WorkFilter)}><option value="all">Всех студентов</option><option value="missing">Без работы</option><option value="unreviewed">Ожидают проверки</option><option value="reviewed">Проверенные</option></select></label></div>
    {downloadError&&<p className="notice error-notice" role="alert">{downloadError}</p>}
    <div className="student-table-wrap"><table className="student-table assignment-register"><thead><tr><th>СТУДЕНТ / ID FORMA</th><th>РАБОТА</th><th>СХОДСТВО</th><th>AI DETECTOR</th><th>ПРОВЕРКА И ОЦЕНКА</th><th><span className="rw-sr-only">Действия</span></th></tr></thead><tbody>{visible.map(row=>{
      const work=row.latest,match=work?fileMatchFor(work.id,comparison):null;
      return <tr key={row.student_id}><td data-label="Студент / ID Forma"><strong>{row.student_name}</strong><code className="assignment-student-id">{row.student_id}</code>{!row.active&&<small>Больше не записан на курс</small>}</td><td data-label="Работа">{work?<><Link className="assignment-file" href={`/teacher/submissions/${work.id}/review?panel=document`}>{work.file_name} ↗</Link><small>{date(work.submitted_at)} · {(work.file_type||'файл').toUpperCase()}</small><small>ID работы: {work.id}</small>{row.attempts.length>1&&<details><summary>Предыдущие попытки · {row.attempts.length-1}</summary>{row.attempts.slice(1).map(old=><div className="assignment-attempt" key={old.id}><Link href={`/teacher/submissions/${old.id}/review`}>{old.file_name} →</Link><small>{date(old.submitted_at)} · {humanReviewLabel(old)}</small><Link href={`/teacher/submissions/${old.id}/originality`}>Текст: {textSimilarityLabel(old.similarity)}</Link></div>)}</details>}</>:<span>Работа не отправлена</span>}</td><td data-label="Сходство">{work?<>{match?<><Link className="assignment-text-score" href={comparisonUrl(work.id,match.candidateId)}>{Math.round(match.score*100)}%</Link><small>Индекс сходства файлов</small></>:<><Link className="assignment-text-score" href={`/teacher/submissions/${work.id}/originality`}>{textSimilarityLabel(work.similarity)}</Link><small>Текст · доступный архив</small></>}</>:<span>—</span>}</td><td data-label="AI detector">{work?<IntegritySignal submissionId={work.id} value={work.integrity}/>:<span>—</span>}</td><td data-label="Проверка и оценка">{work?<><strong>{humanReviewLabel(work)}</strong>{work.has_draft&&work.review_status!=='draft'&&<small>Есть более новый черновик</small>}<small>{aiProcessingLabel(work.processing_status)}</small></>:<span>Ожидается сдача</span>}</td><td data-label="Действия">{work&&<div className="assignment-work-actions"><Link className="button primary" href={`/teacher/submissions/${work.id}/review?panel=assessment`}>Проверить →</Link><button className="quiet-button" onClick={()=>void download(work)}>Скачать оригинал</button></div>}</td></tr>;
    })}</tbody></table></div>
    {!visible.length&&<p className="student-empty">{rows.length?'По выбранным фильтрам студентов нет.':'В курсе пока нет студентов и отправленных работ.'}</p>}
    <p className="integrity-advisory">{INTEGRITY_NOTE}</p><p className="muted">Процент относится к указанному виду сравнения: файлы задания или текст доступного архива. Отсутствие отчёта не считается 0%.</p>
  </section>;
}
export function AssignmentWorkspace({assignmentId}:{assignmentId:string}){
  const [data,setData]=useState<Workspace|null>(null),[error,setError]=useState(''),[actionError,setActionError]=useState(''),[retry,setRetry]=useState(0),[refreshing,setRefreshing]=useState(false),[exporting,setExporting]=useState(false);
  const [comparison,setComparison]=useState<Comparison|null>(null);
  const onComparison=useCallback((result:Comparison)=>setComparison(result),[]);
  const exportBusy=useRef(false);
  useEffect(()=>{let active=true,pending=false;setData(null);setError('');async function load(){if(pending)return;pending=true;try{const value=await platformRequest<Workspace>(`/api/assignment-submissions/${assignmentId}`);if(active){setData(value);setError('');}}catch(e){if(active)setError(e instanceof Error?e.message:'Не удалось загрузить задание.');}finally{pending=false;if(active)setRefreshing(false);}}
    void load();const timer=window.setInterval(()=>void load(),15000);return()=>{active=false;window.clearInterval(timer);};},[assignmentId,retry]);
  async function exportGrades(){if(exportBusy.current)return;exportBusy.current=true;setExporting(true);setActionError('');try{await downloadAuthenticatedFile(`/api/review-pilot/assignments/${assignmentId}/grades.csv`,`forma-grades-${assignmentId}.csv`);}catch{setActionError('Не удалось выгрузить опубликованные оценки.');}finally{exportBusy.current=false;setExporting(false);}}
  const students=data?studentWorks(data):[],active=students.filter(s=>s.active),submitted=active.filter(s=>s.latest),reviewed=students.filter(s=>s.latest&&['confirmed','published'].includes(s.latest.review_status));
  return <div className="assignment-workspace"><div className="breadcrumbs-inline"><Link href="/teacher">Курсы</Link><span>/</span>{data&&<><Link href={`/teacher/courses/${data.offering_id}/assignments`}>{data.course_code} · {data.course_name}</Link><span>/</span></>}<span>Задание</span></div>
    <section className="academic-heading"><div><div className="eyebrow">ЗАДАНИЕ · РАБОТЫ И ПРОВЕРКА</div><h1>{data?.title??'Задание'}</h1>{data&&<p>Срок: {date(data.due_at)} · Максимум: {data.maximum_score} баллов</p>}</div><button className="button" disabled={refreshing} onClick={()=>{setRefreshing(true);setRetry(n=>n+1);}}>Обновить</button></section>
    {error&&<div className="notice error-notice" role="alert">{data?'Не удалось обновить данные. Ниже последняя загруженная версия. ':''}{error}<button className="button" onClick={()=>setRetry(n=>n+1)}>Повторить</button></div>}
    {actionError&&<p className="notice error-notice" role="alert">{actionError}</p>}
    {!data&&!error&&<p role="status">Загружаем задание, студентов и работы…</p>}
    {data&&<><div className="assignment-stat-strip"><div><strong>{active.length}</strong><span>студентов в группе</span></div><div><strong>{submitted.length}</strong><span>отправили работу</span></div><div><strong>{active.length-submitted.length}</strong><span>ожидается сдача</span></div><div><strong>{reviewed.length}</strong><span>последних работ проверено</span></div></div>
      <div className="rw-pilot-links"><Link className="button" href={`/teacher/assignments/${assignmentId}/question-review`}>Проверка по вопросам →</Link><button className="button" disabled={exporting} onClick={()=>void exportGrades()}>{exporting?'Выгружаем…':'Опубликованные оценки · CSV'}</button></div>
      <details className="assignment-instructions"><summary>Условия и материалы задания</summary><p className="assignment-context">{data.description||'Дополнительные инструкции не указаны.'}</p><AssignmentTemplate offeringId={data.offering_id} assignmentId={assignmentId}/><AssignmentBriefs assignmentId={assignmentId}/></details>
      <AssignmentRegister data={data} comparison={comparison}/><ComparisonPanel assignmentId={assignmentId} students={students} revision={data.comparison_revision} onResult={onComparison}/>
    </>}
  </div>;
}
