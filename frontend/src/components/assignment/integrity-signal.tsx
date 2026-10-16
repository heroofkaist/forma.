"use client";
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { platformRequest } from '../../lib/platform';
import { detectorLabel, INTEGRITY_NOTE, type IntegrityReport, type IntegritySummary } from '../../lib/document-integrity';

export function IntegrityDialog({ submissionId, onClose }: { submissionId: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null), sending = useRef(false);
  const [data, setData] = useState<IntegrityReport | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  useEffect(() => { const node = dialog.current!; const previous = document.activeElement as HTMLElement | null; node.showModal(); return () => { node.close(); previous?.focus(); }; }, []);
  useEffect(() => { let active = true; let pending = false; const load = async () => { if(pending)return;pending=true; try { const value=await platformRequest<IntegrityReport>(`/api/document-integrity/${submissionId}`); if(active){setData(value);setError('');} } catch { if(active)setError('Не удалось загрузить отчёт. Попробуйте открыть его ещё раз.'); } finally{pending=false;} }; void load(); const timer=window.setInterval(()=>void load(),8000);return()=>{active=false;window.clearInterval(timer);}; }, [submissionId]);
  async function run() { if(sending.current)return;sending.current=true;setBusy(true);setError('');try{await platformRequest(`/api/document-integrity/${submissionId}`,{force:data?.status==='failed'});setData({status:'queued'});}catch(e){setError(e instanceof Error?e.message:'Не удалось запустить анализ.');}finally{sending.current=false;setBusy(false);} }
  const running = data && ['queued','extracting','interpreting'].includes(data.status);
  return <dialog ref={dialog} className="integrity-dialog" aria-labelledby="integrity-title" onCancel={event=>{event.preventDefault();onClose();}}><header><div><span className="eyebrow">ЛОКАЛЬНЫЙ АНАЛИЗ · БЕСПЛАТНО</span><h2 id="integrity-title">AI detector</h2></div><button type="button" className="quiet-button" onClick={onClose} autoFocus>Закрыть</button></header>
    <p className="integrity-advisory">{INTEGRITY_NOTE}</p><p>Алгоритм проверяет извлечённый текст: ищет служебную разметку ИИ, самоупоминания модели и длинные повторы. Он не определяет авторство и не расходует AI-токены.</p>
    {error&&<p role="alert" className="notice error-notice">{error}</p>}{!data&&!error&&<p role="status">Загружаем сохранённый отчёт…</p>}
    {data&&<><strong className="integrity-result">{detectorLabel(data)}</strong>{data.report&&<p className="muted">Проверено страниц / разделов с текстом: {data.report.units_analyzed} из {data.report.units_total}. Слов в тексте: {data.report.metrics?.word_count ?? '—'}.</p>}
      {data.report?.style_signals.map((signal,index)=><article className="integrity-observation" key={index}><Link href={`/teacher/submissions/${submissionId}/review?page=${signal.unit}`}>Оригинал · раздел {signal.unit}</Link><blockquote>{signal.quote}</blockquote><p>{signal.observation}</p><p className="muted">Возможное объяснение: {signal.alternative_explanation}</p></article>)}
      {data.report?.limitations && <section className="integrity-limitations"><h3>Как читать результат</h3>{data.report.limitations.map((text,index)=><p className="muted" key={index}>{text}</p>)}</section>}
      {['not_analyzed','stale','awaiting_budget','failed'].includes(data.status)&&<div className="integrity-run"><p>Работает на сервере без обращения к языковой модели. Стоимость — $0.</p><button type="button" className="button primary" disabled={busy||Boolean(running)} onClick={()=>void run()}>{busy?'Ставим в очередь…':'Проверить текст'}</button></div>}
      {data.status==='input_limit'&&<p>Объём текста превышает лимит локального анализа (500 КБ). Результат не рассчитан.</p>}
    </>}
  </dialog>;
}
export function IntegritySignal({ submissionId, value }: { submissionId: string; value?: IntegritySummary | null }) {
  const [open,setOpen]=useState(false);
  return <><button type="button" className="integrity-status" onClick={()=>setOpen(true)}>{detectorLabel(value)}</button><small>Локальная проверка текста</small>{open&&<IntegrityDialog submissionId={submissionId} onClose={()=>setOpen(false)}/>}</>;
}
