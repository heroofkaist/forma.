"use client";
import { useState } from 'react';
import Link from 'next/link';
import { platformRequest } from '../../lib/platform';
import type { CriterionView, ReviewResponse, ReviewEditor, EditorValue } from '../../lib/review-workspace';
import { appendCardExplanation } from '../../lib/review-pilot';
import type { DecisionCard } from '../../lib/review-pilot';

export function DecisionMemory({data, criteria, editor, rubricId, busy: workspaceBusy, onApply}: {data: ReviewResponse; criteria: CriterionView[]; editor: ReviewEditor; rubricId?: string; busy: boolean; onApply: (key: string, patch: Partial<EditorValue>) => void}) {
  const [key,setKey] = useState(criteria[0]?.key ?? '');
  const [cards,setCards] = useState<DecisionCard[]>([]);
  const [loaded,setLoaded] = useState(false); const [busy,setBusy] = useState(false);
  const [error,setError] = useState(''); const [message,setMessage] = useState('');
  const [title,setTitle] = useState(''); const [rule,setRule] = useState(''); const [reference,setReference] = useState(false);
  const [page,setPage] = useState('1'); const [observation,setObservation] = useState('');
  const criterion=criteria.find(c=>c.key===key); const saved=data.reviews[0];
  const savedScore=saved?.criteria.find(c=>c.question_id===criterion?.question_id && c.criterion_id===criterion?.criterion_id);
  const canSave=!!savedScore && savedScore.confirmed!==false && savedScore.points!=null;
  const validEvidence=Number.isInteger(Number(page)) && Number(page)>=1 && Number(page)<=(data.file_type==='pdf'?data.structure?.pages.length ?? 0:0) && observation.trim().length>0;
  async function load() {
    if(!criterion)return;setBusy(true);setError('');setCards([]);setLoaded(false);
    try { const query=new URLSearchParams({question_id:criterion.question_id,criterion_id:criterion.criterion_id}); if(rubricId)query.set('rubric_id',rubricId); const result=await platformRequest<{items:DecisionCard[]}>(`/api/review-pilot/submissions/${data.submission_id}/cards?${query}`);setCards(result.items);setLoaded(true); }
    catch(cause){setError(cause instanceof Error?cause.message:'Не удалось загрузить карточки.');}finally{setBusy(false);}
  }
  async function save() {
    if(!criterion || !saved || !validEvidence || !canSave)return;setBusy(true);setError('');setMessage('');
    try { await platformRequest(`/api/review-pilot/submissions/${data.submission_id}/cards`,{review_id:saved.id,question_id:criterion.question_id,criterion_id:criterion.criterion_id,title,rule,kind:reference?'reference':'decision',evidence:{page_number:Number(page),observation}});setMessage('Карточка сохранена из подтверждённого решения. Оценки не изменены.');setTitle('');setRule('');await load(); }
    catch(cause){setError(cause instanceof Error?cause.message:'Не удалось сохранить карточку.');}finally{setBusy(false);}
  }
  const disabled=busy || workspaceBusy;
  return <details className="rw-detail rw-pilot-panel"><summary>Память решений и примеры-ориентиры</summary><p className="rw-muted">Карточки доступны только преподавателям этого курса при совпадении версии критерия. Применение переносит объяснение в редактор; балл вы назначаете отдельно.</p>
    <label>Критерий<select value={key} disabled={disabled} onChange={e=>{setKey(e.target.value);setCards([]);setLoaded(false);setError('');setMessage('');}}>{criteria.map(c=><option value={c.key} key={c.key}>{c.description}</option>)}</select></label>
    <button className="rw-button" type="button" disabled={!criterion || disabled} onClick={()=>void load()}>{busy?'Загружаем…':'Найти совместимые карточки'}</button>
    <fieldset disabled={disabled}><legend>Основание в текущей работе</legend><p className="rw-muted">Укажите страницу оригинала и собственное наблюдение. Это ручная запись, а не проверенная машиной цитата.</p><label>Страница<input type="number" min={1} max={data.structure?.pages.length ?? 0} step={1} value={page} onChange={e=>setPage(e.target.value)}/></label><label>Наблюдение<textarea maxLength={2000} rows={2} value={observation} onChange={e=>setObservation(e.target.value)}/></label></fieldset>
    {loaded && !cards.length && <p role="status">Для этого критерия карточек пока нет.</p>}
    {cards.map(card=><article className="rw-detail" key={card.id}><h3>{card.title}{card.kind==='reference'?' · Ориентир':''}</h3><p>{card.rule}</p><p>{card.feedback}</p><p className="rw-muted">В примере: {card.points} балла · {card.created_by}</p><blockquote><p>Страница {card.evidence.page_number} · {card.evidence.observation}</p></blockquote><Link className="rw-text-button" href={`/teacher/submissions/${encodeURIComponent(card.source_submission_id)}/review?page=${card.evidence.page_number}`} target="_blank" rel="noopener noreferrer">Оригинал примера ↗</Link><button className="rw-button" type="button" disabled={!validEvidence || disabled || !criterion} onClick={()=>{if(!criterion)return;const old=editor.criteria[key];const feedback=appendCardExplanation(old.feedback,card.feedback || card.rule);if(feedback.length>4000){setError('Комментарий превысит 4000 символов. Сократите его перед применением.');return;}onApply(key,{feedback,card_use:{card_id:card.id,evidence:{page_number:Number(page),observation}}});setMessage('Объяснение добавлено в редактор. Проверьте его и сохраните решение. Балл не перенесён.');}}>Применить с новым основанием</button></article>)}
    {criterion && editor.criteria[key]?.card_use && <p className="rw-muted">К решению привязана карточка и новое основание. <button className="rw-text-button" type="button" disabled={disabled} onClick={()=>onApply(key,{card_use:null})}>Убрать связь</button></p>}
    <details><summary>Сохранить своё подтверждённое решение</summary><p className="rw-muted">Используется последняя сохранённая проверка, а не несохранённые поля. Сначала подтвердите решение по критерию.</p><label>Короткое название<input maxLength={160} value={title} disabled={disabled} onChange={e=>setTitle(e.target.value)}/></label><label>Правило и объяснение<textarea maxLength={2000} value={rule} disabled={disabled} onChange={e=>setRule(e.target.value)}/></label><label className="rw-pilot-check"><input type="checkbox" checked={reference} disabled={disabled} onChange={e=>setReference(e.target.checked)}/>Использовать как пример-ориентир</label><button className="rw-button" type="button" disabled={disabled || !canSave || !validEvidence || !title.trim() || !rule.trim()} onClick={()=>void save()}>Сохранить карточку</button></details>
    {error && <p className="rw-alert" role="alert">{error}</p>}{message && <p className="rw-notice" role="status">{message}</p>}
  </details>;
}
