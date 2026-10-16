"use client";
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { platformRequest } from '../../lib/platform';
import type { ReviewResponse } from '../../lib/review-workspace';
import {questionReviewUrl,type PageMapping,type QuestionQueue} from '../../lib/review-pilot';

export function QuestionReviewNavigation({data, question, onQuestion}: {data:ReviewResponse;question:string;onQuestion:(id:string)=>void}) {
  const [queue,setQueue]=useState<QuestionQueue|null>(null);const [error,setError]=useState(false);
  useEffect(()=>{let active=true;setQueue(null);setError(false);if(question)void platformRequest<QuestionQueue>(`/api/review-pilot/assignments/${data.assignment_id}/question-queue?${new URLSearchParams({question_id:question})}`).then(value=>{if(active)setQueue(value);}).catch(()=>{if(active)setError(true);});return()=>{active=false;};},[data.assignment_id,question]);
  const index=queue?.items.findIndex(item=>item.id===data.submission_id) ?? -1;
  const adjacent=[queue?.items[index-1],index>=0?queue?.items[index+1]:undefined];
  return <div className="rw-pilot-panel"><label>Фокус проверки<select value={question} onChange={e=>onQuestion(e.target.value)}><option value="">Все вопросы</option>{data.questions.map(q=><option key={q.id} value={q.id}>{q.title}</option>)}</select></label>
    {question && <><p className="rw-muted">Показаны критерии выбранного вопроса. Сохранение учитывает всю рубрику; неполную работу сохраняйте как черновик.</p><div className="rw-pilot-links">{adjacent.map((item,i)=>item && <Link className="rw-text-button" key={item.id} href={questionReviewUrl(item.id,question,item.mapping?.pages)}>{i===0?'← Предыдущая работа':'Следующая работа →'}</Link>)}<Link href={`/teacher/assignments/${data.assignment_id}/question-review`}>Вся очередь →</Link></div>{error && <p role="alert">Очередь не загрузилась. Проверка этой работы доступна.</p>}</>}
  </div>;
}
export function QuestionPages({ data, busy: workspaceBusy, onPage, onDirty }: {
  data: ReviewResponse;
  busy: boolean;
  onPage: (page: number) => void;
  onDirty: (dirty: boolean) => void;
}) {
  const [qid, setQid] = useState(data.questions[0]?.id ?? '');
  const [mappings, setMappings] = useState<PageMapping[]>([]);
  const [pages, setPages] = useState<number[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const savedPages = mappings.find(m => m.question_id === qid)?.pages ?? [];
  const dirty = loaded && JSON.stringify(pages) !== JSON.stringify(savedPages);
  useEffect(() => { onDirty(dirty); }, [dirty, onDirty]);
  useEffect(() => () => onDirty(false), [onDirty]);

  async function load() {
    if (dirty || busy) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const result = await platformRequest<{ items: PageMapping[] }>(`/api/review-pilot/submissions/${data.submission_id}/pages`);
      setMappings(result.items);
      setPages(result.items.find(m => m.question_id === qid)?.pages ?? []);
      setLoaded(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось загрузить страницы.');
    } finally { setBusy(false); }
  }
  async function save() {
    if (busy) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const result = await platformRequest<PageMapping>(`/api/review-pilot/submissions/${data.submission_id}/pages`, {
        question_id: qid, pages,
        expected_mapping_id: mappings.find(m => m.question_id === qid)?.id ?? null,
      });
      setMappings(items => [...items.filter(m => m.question_id !== qid), result]);
      setMessage('Страницы вопроса сохранены.');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось сохранить страницы.');
    } finally { setBusy(false); }
  }
  if (data.file_type !== 'pdf') return null;
  return <details className="rw-detail rw-pilot-panel">
    <summary>Страницы вопросов · ручная разметка</summary>
    <p className="rw-muted">Страницы отмечает преподаватель. Автоматических предположений о расположении ответа нет. Разметка нужна для очереди одного вопроса.</p>
    <button className="rw-button" disabled={busy || workspaceBusy || dirty} onClick={() => void load()}>{loaded ? 'Перезагрузить разметку' : 'Загрузить разметку'}</button>
    {loaded && <>
      <label>Вопрос<select value={qid} disabled={busy || workspaceBusy || dirty} onChange={e => {
        setQid(e.target.value);
        setPages(mappings.find(m => m.question_id === e.target.value)?.pages ?? []);
        setMessage(''); setError('');
      }}>{data.questions.map(q => <option key={q.id} value={q.id}>{q.title}</option>)}</select></label>
      {mappings.find(m => m.question_id === qid)?.stale && <p role="status">Вопрос изменён. Отметьте страницы заново.</p>}
      <div className="rw-page-mapping">{data.structure?.pages.map(page => <div key={page.number}>
        <label><input type="checkbox" checked={pages.includes(page.number)} disabled={busy || workspaceBusy} onChange={e => {
          setPages(current => e.target.checked ? [...current, page.number].sort((a, b) => a - b) : current.filter(n => n !== page.number));
          setMessage('');
        }}/>Стр. {page.number}</label>
        <button className="rw-text-button" type="button" onClick={() => onPage(page.number)}>Открыть</button>
      </div>)}</div>
      {dirty && <p role="status">Разметка изменена. Сохраните её отдельно или отмените изменения перед выбором другого вопроса.</p>}
      <div className="rw-pilot-links">
        <button className="rw-button" disabled={busy || workspaceBusy || !qid} onClick={() => void save()}>Сохранить страницы</button>
        {dirty && <button className="rw-text-button" disabled={busy || workspaceBusy} onClick={() => {
          setPages(savedPages); setError(''); setMessage('Изменения разметки отменены.');
        }}>Отменить изменения разметки</button>}
      </div>
    </>}
    {error && <p role="alert" className="rw-alert">{error} Выбранные страницы сохранены на экране. При конфликте отмените изменения и перезагрузите разметку.</p>}
    {message && <p role="status">{message}</p>}
  </details>;
}
