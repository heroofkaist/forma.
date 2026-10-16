"use client";
import { useId, useState } from "react";
import { Check, FileText, Pencil, Pause, X } from "lucide-react";
import {scoreLabel,aiText} from "../../lib/teacher-display";
import {SavedComments} from "./saved-comments";
import katex from "katex";
import type { CriterionView, EditorValue, Evidence, Finding, SavedReviewState } from "../../lib/review-workspace";
import { decisionLabels, savedReviewLabels, findingLabels, scoreError } from "../../lib/review-workspace";

/** Render only explicit math delimiters. KaTeX never trusts submitted HTML/commands. */
export function AcademicText({ text }: { text: string }) {
  return <>{text.split(/(\$\$[\s\S]+?\$\$|\$[^$\n]+?\$|\\\([\s\S]+?\\\)|\\\[[\s\S]+?\\\])/g).map((part, i) => {
    const block = part.startsWith("$$") || part.startsWith("\\[");
    if (!part.startsWith("$") && !part.startsWith("\\(") && !part.startsWith("\\[")) return <span key={i}>{part}</span>;
    const math = part.startsWith("$") && !block ? part.slice(1, -1) : part.slice(2, -2);
    return <span key={i} className="rw-math" dangerouslySetInnerHTML={{ __html: katex.renderToString(math, { throwOnError: false, trust: false, strict: "ignore", displayMode: block, maxExpand: 200, maxSize: 10, output: "htmlAndMathml" }) }}/>;
  })}</>;
}
export function EvidenceLink({ evidence, onPage, onEvidence }: { evidence: Evidence; onPage: (page: number) => void; onEvidence?:()=>void }) {
  return <button type="button" className="rw-evidence-link" onClick={() => onEvidence ? onEvidence() : onPage(evidence.page_number)}><FileText size={13}/> Страница {evidence.page_number}<span className="rw-sr-only">, перейти к источнику</span></button>;
}
export function TeacherDecisionEditor({ criterion, value, onChange, manual, busy }: { criterion: CriterionView; value: EditorValue; onChange: (patch: Partial<EditorValue>) => void; manual: boolean; busy: boolean }) {
  const id = useId(); const error = scoreError(value.points, criterion.maximum_points);
  return <div className="rw-decision-editor">
    {!manual && criterion.suggestion && <div className="rw-decision-actions" role="group" aria-label="Решение по предложению">
      <button aria-pressed={value.action === "accepted"} disabled={busy} onClick={() => onChange({ action: "accepted", ...(criterion.suggestion?.proposed_score != null ? { points: String(criterion.suggestion.proposed_score), ...(value.feedback.trim() ? {} : {feedback: [criterion.suggestion.rationale, criterion.suggestion.suggested_improvement].filter(Boolean).join('\n\n')}) } : {}) })}><Check size={14}/> Принять</button>
      <button disabled={busy} onClick={() => { onChange({ action: "accepted" }); document.getElementById(`${id}-feedback`)?.focus(); }}><Pencil size={13}/> Правка</button>
      <button aria-pressed={value.action === "rejected"} disabled={busy} onClick={() => onChange({ action: "rejected", points: "" })}><X size={14}/> Отклонить</button>
      <button aria-pressed={value.action === "deferred"} disabled={busy} onClick={() => onChange({ action: "deferred", points: "" })}><Pause size={13}/> Отложить</button>
    </div>}
    <div className="rw-score-row"><label htmlFor={`${id}-score`}>Ваш балл</label><div><input id={`${id}-score`} inputMode="decimal" type="number" min={0} max={scoreLabel(criterion.maximum_points)} step="any" placeholder="—" value={value.points} disabled={busy || (!manual && value.action !== "accepted")} aria-invalid={!!error} aria-describedby={error ? `${id}-error` : `${id}-hint`} onChange={e => onChange({ points: e.target.value })}/><span>/ {scoreLabel(criterion.maximum_points)}</span></div></div>
    {error ? <p className="rw-field-error" id={`${id}-error`}>{error}</p> : <p className="rw-input-hint" id={`${id}-hint`}>{manual || value.action === "accepted" ? "Укажите балл по этому критерию." : value.action === "rejected" ? "Предложение исключено. Независимую оценку можно сохранить в ручном режиме." : "Выберите «Принять» или переключитесь на самостоятельную оценку."}</p>}
    <label className="rw-label" htmlFor={`${id}-feedback`}>Комментарий к критерию</label><textarea id={`${id}-feedback`} rows={2} maxLength={4000} disabled={busy} value={value.feedback} placeholder="Что получилось и что стоит исправить…" onChange={e => onChange({ feedback: e.target.value })}/>
    {!manual && <label className="rw-finding-select">Тип обратной связи<select id={`${id}-finding`} value={value.finding} disabled={busy} onChange={e => onChange({ finding: e.target.value as Finding })}>{Object.entries(findingLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>}
  </div>;
}
export function RubricCriterionCard({ criterion, index, value, onChange, onPage, onEvidence, onRecheck, comments, manual, busy, dirty, savedState }: { onEvidence?:(criterion:CriterionView,index:number)=>void; onRecheck?:(criterion:CriterionView)=>void; comments?:{submissionId:string;rubricId?:string}; criterion: CriterionView; index: number; value: EditorValue; onChange: (patch: Partial<EditorValue>) => void; onPage: (page: number) => void; manual: boolean; busy: boolean; dirty: boolean; savedState: SavedReviewState }) {
  const [showSuggestion, setShowSuggestion] = useState(false);
  const suggestion = criterion.suggestion;
  const score = scoreLabel(suggestion?.proposed_score,criterion.maximum_points);
  const status = dirty ? "Изменено" : manual ? value.points === "" ? "Без оценки" : savedReviewLabels[savedState] : criterion.saved?.confirmed === false ? "Черновик" : decisionLabels[value.action];
  return <article id={`review-criterion-${encodeURIComponent(criterion.question_id)}-${encodeURIComponent(criterion.criterion_id)}`} tabIndex={-1} className="rw-criterion rw-criterion-visible" aria-labelledby={`criterion-${index}-title`}>
    <header className="rw-criterion-heading">
      <span className="rw-criterion-number">{String(index + 1).padStart(2, "0")}</span>
      <div className="rw-criterion-main"><h3 id={`criterion-${index}-title`} className="rw-criterion-title">{criterion.description}</h3><span className="rw-criterion-meta">До {scoreLabel(criterion.maximum_points)} баллов</span></div>
      <div className={`rw-ai-score ${suggestion?.proposed_score == null ? 'is-empty' : ''}`} aria-label={`Балл ИИ: ${score==='—'?'не выставлен':score}`}><span>Оценка ИИ</span><strong>{score}<small> / {scoreLabel(criterion.maximum_points)}</small></strong></div>
      <span className={`rw-status ${!dirty && ["confirmed", "published"].includes(savedState) ? "is-reviewed" : ""}`}>{status}</span>
    </header>
    <div className="rw-criterion-body">
      {suggestion && <section className="rw-assistant-note" aria-label="Подсказка ИИ">
        <div className="rw-assistant-note-heading"><div><strong>{suggestion.proposed_score == null ? 'ИИ не выставил балл' : findingLabels[suggestion.finding]}</strong></div><button type="button" className="rw-text-button" aria-expanded={showSuggestion} onClick={() => setShowSuggestion(v => !v)}>{showSuggestion ? "Скрыть разбор" : "Разбор и цитаты"}</button></div>
        <p className="rw-ai-rationale"><AcademicText text={aiText(suggestion.rationale,"Обоснование недоступно. Сверьте критерий с оригиналом.")}/></p>
        {suggestion.proposed_score == null && <p className="rw-input-hint">{aiText(suggestion.missing_evidence[0]) || aiText(suggestion.uncertainty[0]) || 'Недостаточно данных для оценки. Сверьте ответ с оригиналом.'}</p>}
        {manual && suggestion.proposed_score != null && <button type="button" className="rw-text-button" disabled={busy} onClick={() => onChange({ action: 'accepted', points: String(suggestion.proposed_score), ...(value.feedback.trim() ? {} : {feedback: [suggestion.rationale, suggestion.suggested_improvement].filter(Boolean).join('\n\n')}) })}>Использовать {score} / {scoreLabel(criterion.maximum_points)}</button>}
        {showSuggestion && <div className="rw-assistant-explanation">
          <section><h4>Что замечено в работе</h4><p><AcademicText text={aiText(suggestion.interpretation)}/></p><p><AcademicText text={aiText(suggestion.rationale,"Обоснование недоступно. Сверьте критерий с оригиналом.")}/></p></section>
          <section><h4>Фрагменты оригинала</h4>{suggestion.evidence.length ? suggestion.evidence.map((e, i) => <blockquote key={i}><EvidenceLink evidence={e} onPage={onPage} onEvidence={onEvidence?()=>onEvidence(criterion,i):undefined}/><p><AcademicText text={e.quote}/></p></blockquote>) : <p>Фрагменты не указаны. Сверьте вывод с оригиналом.</p>}</section>
          {(suggestion.suggested_improvement || suggestion.missing_evidence.length || suggestion.uncertainty.length) ? <section><h4>Что стоит проверить</h4><p><AcademicText text={aiText(suggestion.suggested_improvement)}/></p>{[...suggestion.missing_evidence, ...suggestion.uncertainty].map(text=>aiText(text)).filter(Boolean).map((text, i) => <p key={i}>{text}</p>)}</section> : null}
        </div>}
      </section>}
      {suggestion&&onRecheck&&<button className="rw-text-button rw-recheck" type="button" disabled={busy} onClick={()=>onRecheck(criterion)}>Перепроверить только этот критерий</button>}
      <TeacherDecisionEditor criterion={criterion} value={value} onChange={onChange} manual={manual} busy={busy}/>
      {comments&&<SavedComments {...comments} questionId={criterion.question_id} criterionId={criterion.criterion_id} value={value.feedback} onChange={feedback=>onChange({feedback})} disabled={busy}/>}
    </div>
  </article>;
}
