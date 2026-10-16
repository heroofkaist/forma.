"use client";
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { platformRequest } from '../../lib/platform';
import type { ReviewResponse } from '../../lib/review-workspace';
import {questionReviewUrl,type PageMapping,type QuestionQueue} from '../../lib/review-pilot';

export function QuestionReviewNavigation({data, question, onQuestion,criterion="",onCriterion}: {data:ReviewResponse;question:string;onQuestion:(id:string)=>void;criterion?:string;onCriterion?:(id:string)=>void}) {
  const [queue,setQueue]=useState<QuestionQueue|null>(null);const [error,setError]=useState(false);
  useEffect(()=>{let active=true;setQueue(null);setError(false);if(question)void platformRequest<QuestionQueue>(`/api/review-pilot/assignments/${data.assignment_id}/question-queue?${new URLSearchParams({question_id:question})}`).then(value=>{if(active)setQueue(value);}).catch(()=>{if(active)setError(true);});return()=>{active=false;};},[data.assignment_id,question]);
  const index=queue?.items.findIndex(item=>item.id===data.submission_id) ?? -1;
  const adjacent=[queue?.items[index-1],index>=0?queue?.items[index+1]:undefined];
  const url=(item:NonNullable<typeof adjacent[number]>)=>questionReviewUrl(item.id,question,item.mapping?.pages)+(criterion?`&criterion=${encodeURIComponent(criterion)}`:'');
  useEffect(()=>{const handler=(event:KeyboardEvent)=>{if(!event.altKey||event.ctrlKey||event.metaKey||event.shiftKey)return;const item=event.key==='ArrowRight'?adjacent[1]:event.key==='ArrowLeft'?adjacent[0]:undefined;if(item){event.preventDefault();document.querySelector<HTMLAnchorElement>(`a[data-queue-id="${item.id}"]`)?.click();}};window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler);},[queue,criterion,question]);
  return <div className="rw-question-navigation"><div className="rw-question-filters" role="group" aria-label="Вопросы задания"><button type="button" aria-pressed={!question} onClick={() => onQuestion("")}>Все вопросы</button>{data.questions.map(q => <button type="button" key={q.id} aria-pressed={question === q.id} onClick={() => onQuestion(q.id)}>{q.title}</button>)}</div>
    {question&&onCriterion&&<label className="rw-question-criterion">Критерий<select value={criterion} onChange={e=>onCriterion(e.target.value)}><option value="">Все критерии вопроса</option>{data.questions.find(q=>q.id===question)?.criteria.map(c=><option value={c.criterion_id} key={c.criterion_id}>{c.description}</option>)}</select></label>}
    {question && <><p className="rw-muted">Работа {index+1} из {queue?.items.length??"…"}. Переход между студентами: Alt + ← / →. Показаны критерии выбранного вопроса. Сохранение учитывает всю рубрику; неполную работу сохраняйте как черновик.</p><div className="rw-pilot-links">{adjacent.map((item,i)=>item && <Link className="rw-text-button" key={item.id} data-queue-id={item.id} href={url(item)}>{i===0?'← Предыдущая работа':'Следующая работа →'}</Link>)}<Link href={`/teacher/assignments/${data.assignment_id}/question-review`}>Вся очередь →</Link></div>{error && <p role="alert">Очередь не загрузилась. Проверка этой работы доступна.</p>}</>}
  </div>;
}
export function QuestionPages({ data, busy: workspaceBusy, onPage, onDirty, initialQuestionId, reveal = false, embedded = false }: {
  data: ReviewResponse;
  busy: boolean;
  onPage: (page: number) => void;
  onDirty: (dirty: boolean) => void;
  initialQuestionId?: string;
  reveal?: boolean;
  embedded?: boolean;
}) {
  const [qid, setQid] = useState(data.questions.find(q => q.id === initialQuestionId)?.id ?? data.questions[0]?.id ?? '');
  const [mappings, setMappings] = useState<PageMapping[]>([]);
  const [suggestions,setSuggestions]=useState<{question_id:string;pages:number[];confirmed:boolean}[]>([]);
  const [pages, setPages] = useState<number[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [open, setOpen] = useState(reveal);
  const section = useRef<HTMLElement>(null);
  const savedPages = mappings.find(m => m.question_id === qid)?.pages ?? [];
  const dirty = loaded && JSON.stringify(pages) !== JSON.stringify(savedPages);
  useEffect(() => { onDirty(dirty); }, [dirty, onDirty]);
  useEffect(() => () => onDirty(false), [onDirty]);
  useEffect(() => {
    if (!reveal || data.file_type !== 'pdf') return;
    section.current?.scrollIntoView({ block: 'start' });
    section.current?.querySelector<HTMLElement>('summary, h3')?.focus({ preventScroll: true });
    void load();
  }, [reveal]);

  async function load() {
    if (dirty || busy) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const result = await platformRequest<{ items: PageMapping[]; suggestions?:{question_id:string;pages:number[];confirmed:boolean}[] }>(`/api/review-pilot/submissions/${data.submission_id}/pages`);
      setMappings(result.items);setSuggestions(result.suggestions??[]);
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
  if(data.questions.length<2)return <section className="rw-pilot-panel"><h3>Вся работа целиком</h3><p>В задании один общий ответ. Все страницы относятся к нему; отдельная разметка не нужна.</p><button className="rw-button" onClick={()=>onPage(1)}>Открыть начало работы</button></section>;
  const content = <>
    {!embedded && <summary>Страницы вопросов · ручная разметка</summary>}
    <p className="rw-muted">Укажите, где находится решение выбранной задачи. Это навигация по работе; баллы и критерии здесь не меняются.</p>
    <button className="rw-button" disabled={busy || workspaceBusy || dirty} onClick={() => void load()}>{loaded ? 'Обновить' : 'Открыть страницы задач'}</button>
    {loaded && <>
      <label>Задача<select value={qid} disabled={busy || workspaceBusy || dirty} onChange={e => {
        setQid(e.target.value);
        setPages(mappings.find(m => m.question_id === e.target.value)?.pages ?? []);
        setMessage(''); setError('');
      }}>{data.questions.map(q => <option key={q.id} value={q.id}>{q.title}</option>)}</select></label>
      {mappings.find(m => m.question_id === qid)?.stale && <p role="status">Вопрос изменён. Отметьте страницы заново.</p>}
      {suggestions.find(s=>s.question_id===qid)?.pages.length ? <div className="rw-page-suggestion"><p>Распознавание нашло ответ на страницах {suggestions.find(s=>s.question_id===qid)!.pages.join(', ')}. Сверьте с оригиналом.</p><button className="rw-button" disabled={busy||workspaceBusy} onClick={()=>setPages(suggestions.find(s=>s.question_id===qid)!.pages)}>Использовать найденные страницы</button></div> : <p className="rw-muted">Готовой привязки пока нет. Выберите страницы ниже или запустите разбор ответов в разделе «Помощь ИИ».</p>}
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
  </>;
  return embedded ? <section id="rw-question-pages" ref={section} className="rw-pilot-panel"><h3 tabIndex={-1}>Где находится решение задачи</h3>{content}</section> : <details id="rw-question-pages" ref={section as React.RefObject<HTMLDetailsElement>} open={open} onToggle={e => setOpen(e.currentTarget.open)} className="rw-detail rw-pilot-panel">{content}</details>;
}
