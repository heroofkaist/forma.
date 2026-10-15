"use client";
import { useId } from "react";
import { Check, ChevronDown, FileText, Pencil, Pause, X } from "lucide-react";
import katex from "katex";
import type { CriterionView, EditorValue, Evidence, Finding } from "../../lib/review-workspace";
import { decisionLabels, findingLabels, scoreError, shortSummary } from "../../lib/review-workspace";

/** Render only explicit math delimiters. KaTeX never trusts submitted HTML/commands. */
export function AcademicText({ text }: { text: string }) {
  return <>{text.split(/(\$\$[\s\S]+?\$\$|\$[^$\n]+?\$|\\\([\s\S]+?\\\)|\\\[[\s\S]+?\\\])/g).map((part, i) => {
    const block = part.startsWith("$$") || part.startsWith("\\[");
    if (!part.startsWith("$") && !part.startsWith("\\(") && !part.startsWith("\\[")) return <span key={i}>{part}</span>;
    const math = part.startsWith("$") && !block ? part.slice(1, -1) : part.slice(2, -2);
    return <span key={i} className="rw-math" dangerouslySetInnerHTML={{ __html: katex.renderToString(math, { throwOnError: false, trust: false, strict: "ignore", displayMode: block, maxExpand: 200, maxSize: 10, output: "htmlAndMathml" }) }}/>;
  })}</>;
}
export function EvidenceLink({ evidence, onPage }: { evidence: Evidence; onPage: (page: number) => void }) {
  return <button type="button" className="rw-evidence-link" onClick={() => onPage(evidence.page_number)}><FileText size={13}/> Страница {evidence.page_number}<span className="rw-sr-only">, перейти к источнику</span></button>;
}
export function TeacherDecisionEditor({ criterion, value, onChange, manual, busy }: { criterion: CriterionView; value: EditorValue; onChange: (patch: Partial<EditorValue>) => void; manual: boolean; busy: boolean }) {
  const id = useId(); const error = scoreError(value.points, criterion.maximum_points);
  return <div className="rw-decision-editor">
    {!manual && criterion.suggestion && <div className="rw-decision-actions" role="group" aria-label="Решение по предложению">
      <button aria-pressed={value.action === "accepted"} disabled={busy} onClick={() => onChange({ action: "accepted" })}><Check size={14}/> Принять</button>
      <button disabled={busy} onClick={() => { onChange({ action: "accepted" }); document.getElementById(`${id}-feedback`)?.focus(); }}><Pencil size={13}/> Правка</button>
      <button aria-pressed={value.action === "rejected"} disabled={busy} onClick={() => onChange({ action: "rejected", points: "" })}><X size={14}/> Отклонить</button>
      <button aria-pressed={value.action === "deferred"} disabled={busy} onClick={() => onChange({ action: "deferred", points: "" })}><Pause size={13}/> Отложить</button>
    </div>}
    <div className="rw-score-row"><label htmlFor={`${id}-score`}>Балл преподавателя</label><div><input id={`${id}-score`} inputMode="decimal" type="number" min={0} max={criterion.maximum_points} step="any" placeholder="—" value={value.points} disabled={busy || (!manual && value.action !== "accepted")} aria-invalid={!!error} aria-describedby={error ? `${id}-error` : `${id}-hint`} onChange={e => onChange({ points: e.target.value })}/><span>/ {criterion.maximum_points}</span></div></div>
    {error ? <p className="rw-field-error" id={`${id}-error`}>{error}</p> : <p className="rw-input-hint" id={`${id}-hint`}>{manual || value.action === "accepted" ? "Укажите собственную оценку. Предложение модели не переносится автоматически." : value.action === "rejected" ? "Предложение исключено. Независимую оценку можно сохранить в ручном режиме." : "Примите предложение или выберите ручную проверку, чтобы указать балл."}</p>}
    <label className="rw-label" htmlFor={`${id}-feedback`}>Комментарий преподавателя</label><textarea id={`${id}-feedback`} rows={3} maxLength={4000} disabled={busy} value={value.feedback} placeholder="Ваше обоснование и обратная связь…" onChange={e => onChange({ feedback: e.target.value })}/>
    {!manual && <details className="rw-small-details"><summary>Уточнить тип наблюдения</summary><label className="rw-sr-only" htmlFor={`${id}-finding`}>Тип наблюдения преподавателя</label><select id={`${id}-finding`} value={value.finding} onChange={e => onChange({ finding: e.target.value as Finding })}>{Object.entries(findingLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></details>}
  </div>;
}
export function RubricCriterionCard({ criterion, index, value, open, onOpen, onChange, onPage, manual, busy, dirty }: { criterion: CriterionView; index: number; value: EditorValue; open: boolean; onOpen: () => void; onChange: (patch: Partial<EditorValue>) => void; onPage: (page: number) => void; manual: boolean; busy: boolean; dirty: boolean }) {
  const id = useId(); const suggestion = criterion.suggestion;
  const status = dirty ? "Есть изменения" : manual ? value.points === "" ? "Не оценено" : "Черновик оценки" : criterion.saved?.confirmed === false ? "Сохранённый черновик" : decisionLabels[value.action];
  return <article className={`rw-criterion ${open ? "is-open" : ""}`}>
    <button className="rw-criterion-heading" aria-expanded={open} aria-controls={`${id}-body`} onClick={onOpen}>
      <span className="rw-criterion-number">{String(index + 1).padStart(2, "0")}</span><span className="rw-criterion-main"><span className="rw-criterion-title">{criterion.description}</span><span className="rw-criterion-summary">{shortSummary(suggestion)}</span><span className="rw-criterion-meta"><span>Макс. {criterion.maximum_points}</span><span>ИИ: {suggestion?.proposed_score != null ? `${suggestion.proposed_score} / ${criterion.maximum_points}` : "Нет предложения"}</span></span></span>
      <span className="rw-criterion-end"><span className={`rw-status ${value.action === "accepted" && !dirty && criterion.saved?.confirmed !== false && !manual ? "is-reviewed" : ""}`}>{status}</span><ChevronDown size={15}/></span>
    </button>
    {open && <div className="rw-criterion-body" id={`${id}-body`}>
      {suggestion ? <section className="rw-ai-suggestion" aria-label="Предложение ИИ"><div className="rw-section-eyebrow">ПРЕДЛОЖЕНИЕ ИИ · НЕ ОФИЦИАЛЬНАЯ ОЦЕНКА</div><p className="rw-finding"><span className={`rw-finding-dot ${suggestion.finding}`}/>{findingLabels[suggestion.finding]}</p>
        {suggestion.evidence.length > 0 && <div className="rw-source-chips">{[...new Set(suggestion.evidence.map(e => e.page_number))].map(page => <EvidenceLink key={page} evidence={{ page_number: page, section_id: "", quote: "" }} onPage={onPage}/>)}</div>}
        <details className="rw-detail"><summary>Наблюдаемые источники <span>{suggestion.evidence.length}</span></summary>{suggestion.evidence.length ? suggestion.evidence.map((e, i) => <blockquote key={i}><EvidenceLink evidence={e} onPage={onPage}/><p><AcademicText text={e.quote}/></p></blockquote>) : <p>Подтверждающий фрагмент не указан. Сверьте с оригиналом.</p>}<p className="rw-muted">Транскрипция может содержать ошибки. Цитаты приведены на языке работы.</p></details>
        <details className="rw-detail"><summary>Интерпретация и обоснование</summary><p><AcademicText text={suggestion.interpretation}/></p><p><AcademicText text={suggestion.rationale}/></p></details>
        <details className="rw-detail"><summary>Рекомендации и неопределённость</summary><p><AcademicText text={suggestion.suggested_improvement}/></p>{[...suggestion.missing_evidence, ...suggestion.uncertainty].map((text, i) => <p key={i}><AcademicText text={text}/></p>)}</details>
      </section> : <p className="rw-muted">Для этого критерия нет сохранённого предложения. Оцените работу вручную.</p>}
      <TeacherDecisionEditor criterion={criterion} value={value} onChange={onChange} manual={manual} busy={busy}/>
    </div>}
  </article>;
}
