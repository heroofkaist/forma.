"use client";
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { platformRequest } from '../../lib/platform';
import { detectorLabel, INTEGRITY_NOTE, type IntegrityReport, type IntegritySummary } from '../../lib/document-integrity';

function IntegrityDialog({ submissionId, onClose }: { submissionId: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null), sending = useRef(false);
  const [data, setData] = useState<IntegrityReport | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  useEffect(() => { const node = dialog.current!; const previous = document.activeElement as HTMLElement | null; node.showModal(); return () => { node.close(); previous?.focus(); }; }, []);
  useEffect(() => { let active = true; let pending = false; const load = async () => { if(pending)return;pending=true; try { const value=await platformRequest<IntegrityReport>(`/api/document-integrity/${submissionId}`); if(active){setData(value);setError('');} } catch { if(active)setError('Не удалось загрузить отчёт. Попробуйте открыть его ещё раз.'); } finally{pending=false;} }; void load(); const timer=window.setInterval(()=>void load(),8000);return()=>{active=false;window.clearInterval(timer);}; }, [submissionId]);
  async function run() { if(sending.current)return;sending.current=true;setBusy(true);setError('');try{await platformRequest(`/api/document-integrity/${submissionId}${data?.status==='awaiting_budget'?'/resume':''}`,data?.status==='awaiting_budget'?{}:{force:data?.status==='failed'});setData({status:'queued'});}catch(e){setError(e instanceof Error?e.message:'Не удалось запустить анализ.');}finally{sending.current=false;setBusy(false);} }
  const running = data && ['queued','extracting','interpreting'].includes(data.status);
  return <dialog ref={dialog} className="integrity-dialog" aria-labelledby="integrity-title" onCancel={event=>{event.preventDefault();onClose();}}><header><div><span className="eyebrow">ВСПОМОГАТЕЛЬНЫЙ АНАЛИЗ · QWEN 8B</span><h2 id="integrity-title">AI detector и содержание</h2></div><button type="button" className="quiet-button" onClick={onClose} autoFocus>Закрыть</button></header>
    <p className="integrity-advisory">{INTEGRITY_NOTE}</p><p>Это наблюдения Qwen о тексте, а не калиброванный детектор авторства. Числовая вероятность использования ИИ не рассчитывается.</p>
    {error&&<p role="alert" className="notice error-notice">{error}</p>}{!data&&!error&&<p role="status">Загружаем сохранённый отчёт…</p>}
    {data&&<><strong className="integrity-result">{detectorLabel(data)}</strong>{data.report&&<p className="muted">Проанализировано текстовых частей: {data.report.chunks_analyzed} из {data.report.chunks_total}. Страниц / разделов с текстом: {data.report.units_analyzed} из {data.report.units_total}.</p>}
      {data.report?.style_signals.map((signal,index)=><article className="integrity-observation" key={index}><Link href={`/teacher/submissions/${submissionId}/review?page=${signal.unit}`}>Оригинал · раздел {signal.unit}</Link><blockquote>{signal.quote}</blockquote><p>{signal.observation}</p><p className="muted">Возможное объяснение: {signal.alternative_explanation}</p></article>)}
      {data.report?.features.length ? <section><h3>Содержательные признаки для сравнения</h3>{data.report.features.slice(0,12).map((feature,index)=><article className="integrity-feature" key={index}><strong>{feature.concept}</strong><blockquote>{feature.quote}</blockquote><Link href={`/teacher/submissions/${submissionId}/review?page=${feature.unit}`}>Открыть раздел {feature.unit} →</Link></article>)}</section> : null}
      {['not_analyzed','stale','awaiting_budget','failed'].includes(data.status)&&<div className="integrity-run"><p>Использует общий бюджет Qwen: до $0.02 на файл, до $4 в месяц. Повторный просмотр сохранённого результата бесплатен.</p><button type="button" className="button primary" disabled={busy||Boolean(running)} onClick={()=>void run()}>{busy?'Ставим в очередь…':data.status==='awaiting_budget'?'Продолжить при доступном бюджете':'Проанализировать Qwen'}</button></div>}
      {data.status==='input_limit'&&<p>Файл слишком большой для этого бюджетного анализа. Сравнение текста, страниц и изображений остаётся доступно без ИИ.</p>}
    </>}
  </dialog>;
}
export function IntegritySignal({ submissionId, value }: { submissionId: string; value?: IntegritySummary | null }) {
  const [open,setOpen]=useState(false);
  return <><button type="button" className="integrity-status" onClick={()=>setOpen(true)}>{detectorLabel(value)}</button><small>Экспериментальный сигнал</small>{open&&<IntegrityDialog submissionId={submissionId} onClose={()=>setOpen(false)}/>}</>;
}
