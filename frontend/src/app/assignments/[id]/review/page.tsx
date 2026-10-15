"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import katex from "katex";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ArrowLeft, ArrowRight, Check, ChevronDown, ChevronUp, Download, ExternalLink, LoaderCircle, RotateCcw, Save, Sparkles } from "lucide-react";
import { AppShell, StatusLabel } from "../../../../components/app-shell";
import { ProtectedFileLink, ProtectedImage } from "../../../../components/protected-resource";
import { api } from "../../../../lib/api";
import type { Answer, Assignment, CriterionResult, Grading } from "../../../../lib/types";

type Filter = "all" | "needs_attention";

export default function ReviewWorkspace() {
  const { id } = useParams<{ id: string }>();
  const [assignment, setAssignment] = useState<Assignment | null>(null);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [batchProgress, setBatchProgress] = useState<{ total: number; completed?: number; failed?: number; progress?: number; status?: string } | null>(null);
  const [activeId, setActiveId] = useState("");
  const [grading, setGrading] = useState<Grading | null>(null);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [gradingBusy, setGradingBusy] = useState(false);
  const [showTranscription, setShowTranscription] = useState(true);
  const [filter, setFilter] = useState<Filter>("all");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const activeAnswerRef = useRef("");

  const load = useCallback(async () => {
    try {
      const [task, list, batch] = await Promise.all([api.assignment(id), api.answers(id), api.progress(id)]);
      setAssignment(task);
      setAnswers(list);
      setBatchProgress(batch);
      const requestedStudent = new URLSearchParams(window.location.search).get("student");
      setActiveId((current) => list.some((item) => item.id === current)
        ? current
        : list.find((item) => item.anonymous_student_id === requestedStudent)?.id ?? list[0]?.id ?? "");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить работы.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!answers.some((answer) => ["pending", "processing"].includes(answer.status))) return;
    const timer = window.setInterval(() => void load(), 2500);
    return () => window.clearInterval(timer);
  }, [answers, load]);

  const visible = useMemo(() => filter === "all" ? answers : answers.filter((answer) => answer.status === "needs_attention" || answer.grading?.requires_human_attention || answer.ai_result_json?.requires_human_attention), [answers, filter]);
  const current = visible.find((answer) => answer.id === activeId) ?? visible[0];
  activeAnswerRef.current = current?.id ?? "";
  const question = assignment?.questions.find((item) => item.id === current?.question_id);
  const currentRegion = assignment?.template_regions?.find((region) => region.question_id === current?.question_id);
  const crop = current?.crop_data_url ?? current?.crop_url ?? "";
  const approved = current?.status === "approved";

  useEffect(() => {
    setGrading(null);
    setDirty(false);
    setError("");
    if (!current) return;
    let alive = true;
    api.answer(current.id).then((full) => {
      if (alive) {
        setGrading(full.grading ?? full.ai_result_json ?? null);
        setDirty(false);
      }
    }).catch((cause: unknown) => {
      if (alive) setError(cause instanceof Error ? cause.message : "Не удалось загрузить оценку.");
    });
    return () => { alive = false; };
  }, [current?.id, current?.status]);

  const save = useCallback(async (next: Grading, answerId = current?.id): Promise<boolean> => {
    if (!answerId) return false;
    setSaving(true);
    try {
      const updated = await api.saveReview(answerId, next);
      setAnswers((items) => items.map((item) => item.id === answerId ? { ...item, ...updated } : item));
      if (answerId === activeAnswerRef.current) setDirty(false);
      setMessage("Изменения сохранены");
      window.setTimeout(() => setMessage(""), 1800);
      return true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось сохранить изменения.");
      return false;
    } finally {
      setSaving(false);
    }
  }, [current?.id]);

  useEffect(() => {
    if (!grading || !current || approved || !dirty) return;
    const timer = window.setTimeout(() => void save(grading), 650);
    return () => window.clearTimeout(timer);
  }, [grading, current?.id, approved, dirty, save]);

  const step = useCallback((delta: number) => {
    if (!visible.length) return;
    if (dirty && grading && current) void save(grading, current.id);
    const index = visible.findIndex((item) => item.id === (current?.id ?? activeId));
    const nextIndex = Math.max(0, Math.min(visible.length - 1, index + delta));
    const next = visible[nextIndex];
    if (next) setActiveId(next.id);
  }, [visible, current, activeId, dirty, grading, save]);

  const approve = useCallback(async () => {
    if (!current || !grading) return;
    setError("");
    if (!await save(grading, current.id)) return;
    try {
      await api.approve(current.id);
      setMessage("Оценка утверждена преподавателем");
      await load();
      const index = visible.findIndex((item) => item.id === current.id);
      const next = visible[index + 1];
      if (next) setActiveId(next.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось утвердить оценку.");
    }
  }, [current, grading, save, load, visible]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.target instanceof HTMLElement && ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key.toLowerCase() === "j") step(1);
      if (event.key.toLowerCase() === "k") step(-1);
      if (event.key.toLowerCase() === "a" && !approved && grading) void approve();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step, approve, approved, grading]);

  function editCriterion(index: number, patch: Partial<CriterionResult>) {
    if (!grading) return;
    setDirty(true);
    const criteria = grading.criteria_results.map((item, i) => i === index ? { ...item, ...patch, manually_overridden: true } : item);
    setGrading({ ...grading, criteria_results: criteria, total_points: criteria.reduce((sum, item) => sum + (item.teacher_points ?? item.suggested_points), 0) });
  }

  async function startGrading() {
    setGradingBusy(true);
    setError("");
    try { await api.grade(id); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось запустить оценивание."); }
    finally { setGradingBusy(false); }
  }

  async function retry() {
    if (!current) return;
    setGradingBusy(true);
    setError("");
    try {
      await api.retry(current.id);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось повторить проверку.");
    } finally { setGradingBusy(false); }
  }

  async function retryCrop() {
    if (!current) return;
    if (!currentRegion) {
      setError("Для этого вопроса не найдена сохранённая область. Проверьте шаблон и повторите кроп.");
      return;
    }
    setGradingBusy(true);
    setError("");
    try {
      await api.retryCrop(current.id, current.page_index ?? 0, currentRegion);
      await api.retry(current.id);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось повторно извлечь кроп.");
    } finally {
      setGradingBusy(false);
    }
  }

  if (loading) return <AppShell><div className="table-loading"><span className="spinner" />Открываем проверку…</div></AppShell>;
  return <AppShell>
    <div className="review-topline">
      <div className="breadcrumbs-inline"><Link href="/assignments">Задания</Link><span>/</span><span>{assignment?.title}</span><span>/</span><span>Проверка</span></div>
      <div className="review-top-actions"><Link className="quiet-button" href={`/assignments/${id}/results`}><Download size={14} />Результаты</Link><Link className="quiet-button" href={`/assignments/${id}/template`}>Шаблон</Link></div>
    </div>
    <div className="review-heading">
      <div><div className="eyebrow">{assignment?.subject === "Physics" ? "ФИЗИКА" : "МАТЕМАТИКА"} · ПРОВЕРКА РАБОТ</div><h1>{assignment?.title}</h1><p>{question?.title ?? "Все вопросы"} <span>·</span> {current?.anonymous_student_id ?? "—"}</p></div>
      <div className="review-nav"><span className="review-progress">{current ? visible.findIndex((item) => item.id === current.id) + 1 : 0} <span>/ {visible.length}</span></span><button className="icon-button" onClick={() => step(-1)} disabled={!current || visible.findIndex((item) => item.id === current.id) <= 0} title="Предыдущая (K)"><ArrowLeft size={15} /></button><button className="icon-button" onClick={() => step(1)} disabled={!current || visible.findIndex((item) => item.id === current.id) >= visible.length - 1} title="Следующая (J)"><ArrowRight size={15} /></button></div>
    </div>
    <div className="progress-strip"><span style={{ width: `${answers.length ? answers.filter((item) => item.status === "approved").length / answers.length * 100 : batchProgress?.progress ?? 0}%` }} /></div>
    <div className="review-summary"><span>{answers.filter((item) => item.status === "approved").length} утверждено</span><span>{answers.filter((item) => item.status === "ready_for_review" || item.status === "needs_attention").length} ожидают проверки</span><span>{answers.filter((item) => item.status === "failed").length} с ошибкой</span>{batchProgress && ["grading", "pending", "queued"].includes(batchProgress.status ?? "") && <span className="batch-progress">Оценено {batchProgress.completed ?? 0} / {batchProgress.total}</span>}<button className={filter === "needs_attention" ? "filter-button active" : "filter-button"} onClick={() => setFilter(filter === "all" ? "needs_attention" : "all")}><AlertTriangle size={13} />{filter === "all" ? "Нужно внимание" : "Все работы"}</button></div>
    {error && <div className="notice error-notice">{error}</div>}
    {message && <div className="save-toast">{message}</div>}
    {!current ? <div className="review-empty-state"><h2>{filter === "needs_attention" ? "Нет ответов, требующих внимания" : "Пока нет загруженных ответов"}</h2><p>Сначала добавьте PDF со сканами, чтобы Forma извлекла ответы по шаблону.</p><Link className="button primary" href={`/assignments/${id}/upload`}>Загрузить работы</Link></div> : <section className="review-workspace">
      <div className="evidence-column">
        <div className="evidence-header"><div><strong>Работа студента</strong><span>{current.anonymous_student_id}</span></div><StatusLabel status={current.status} /></div>
        <div className="scan-viewport">{crop ? <ProtectedImage url={crop} alt={`Рукописная работа ${current.anonymous_student_id}`} /> : current.status === "failed" ? <div className="scan-empty"><AlertTriangle size={21} /><span>{current.error || "Не удалось извлечь изображение."}</span><button className="button secondary" onClick={() => void retryCrop()} disabled={gradingBusy}>Повторить кроп и проверку</button><Link href={`/assignments/${id}/template`} className="text-button">Изменить шаблон</Link></div> : <span className="muted">Кроп ещё не готов</span>}</div>
        <div className="scan-tools"><span>ОРИГИНАЛ · ДОКАЗАТЕЛЬСТВО</span>{current.page_number && <span>Стр. {current.page_number}</span>}</div>
        {(crop || current.source_page_url) && <ProtectedFileLink className="open-source" url={current.source_page_url ?? crop}><ExternalLink size={13} />Открыть всю страницу скана</ProtectedFileLink>}
      </div>
      <div className="grading-column">
        <div className="grading-header"><div><strong>Оценка по рубрике</strong><span>{question?.maximum_points ?? 0} баллов максимум</span></div><div className="grading-badges">{grading?.is_demo_output && <span className="demo-tag">ДЕМО · СИМУЛЯЦИЯ</span>}<span className={approved ? "grade-state approved" : "grade-state suggestion"}>{approved ? <Check size={13} /> : <Sparkles size={13} />}{approved ? "Утверждено преподавателем" : "Предложение ИИ"}</span></div></div>
        {(current.status === "pending" || current.status === "processing") && <div className="processing-banner"><LoaderCircle className="spin-icon" size={15} />Обрабатываем ответ. Оценка появится здесь.</div>}
        {(current.status === "failed" || current.status === "needs_attention") && <div className="attention-banner"><AlertTriangle size={15} /><span>{current.error || grading?.attention_reasons?.join(" ") || "Нужна ручная проверка этого ответа."}{grading?.uncertainty !== undefined && grading.uncertainty > 0 ? ` Неуверенность ИИ: ${Math.round(grading.uncertainty * 100)}%.` : ""}</span>{current.status === "failed" && crop && <button className="text-button" onClick={() => void retry()}>Повторить оценку</button>}</div>}
        {grading ? <>
          <div className="transcription-block"><button className="transcription-toggle" onClick={() => setShowTranscription(!showTranscription)}>{showTranscription ? <ChevronUp size={15} /> : <ChevronDown size={15} />}Расшифровка решения<span className={`readability ${grading.transcription_status}`}>{grading.transcription_status === "readable" ? "читается" : grading.transcription_status === "partially_readable" ? "частично читается" : "неразборчиво"}</span></button>{showTranscription && <div className="transcription-body">{renderMath(grading.transcribed_latex || "Расшифровка не предоставлена.")}{grading.transcription_notes && <div className="transcription-note"><AlertTriangle size={13} />{grading.transcription_notes}</div>}</div>}</div>
          <div className="criteria-header"><strong>Критерии</strong><span>ОЦЕНКА / МАКС.</span></div>
          <div className="grading-criteria">{grading.criteria_results.map((criterion, index) => {
            const definition = question?.criteria.find((item) => item.criterion_id === criterion.criterion_id);
            const max = definition?.maximum_points ?? criterion.suggested_points;
            const points = criterion.teacher_points ?? criterion.suggested_points;
            return <article className={`grading-criterion ${criterion.status === "uncertain" ? "is-uncertain" : ""}`} key={criterion.criterion_id}>
              <div className="criterion-topline"><div><strong>{criterion.criterion_id}</strong><span>{definition?.description ?? criterion.criterion_id}</span></div>{criterion.manually_overridden && <span className="override-label">ИЗМЕНЕНО</span>}</div>
              <div className="suggestion-summary">Предложение ИИ: {statusText(criterion.status)} · {criterion.suggested_points} / {max}</div>
              <div className="criterion-controls"><div className="state-options">{(["awarded", "not_awarded", "uncertain"] as const).map((state) => <button key={state} disabled={approved} className={`state-option ${criterion.status === state ? `selected state-${state}` : ""}`} onClick={() => editCriterion(index, { status: state, teacher_points: state === "awarded" ? max : state === "not_awarded" ? 0 : points })}>{state === "awarded" ? "Засчитать" : state === "not_awarded" ? "Не засчитать" : "Не уверен"}</button>)}</div><label className="points-control"><input aria-label={`Баллы ${criterion.criterion_id}`} type="number" min="0" max={max} step="0.5" disabled={approved} value={points} onChange={(event) => editCriterion(index, { teacher_points: Math.max(0, Math.min(max, Number(event.target.value))) })} /><span>/ {max}</span></label></div>
              <textarea className="criterion-explanation-input" aria-label={`Комментарий по критерию ${criterion.criterion_id}`} disabled={approved} rows={2} value={criterion.explanation} onChange={(event) => editCriterion(index, { explanation: event.target.value })} />
              {criterion.evidence_from_solution && <p className="criterion-evidence"><span>ФРАГМЕНТ</span>{criterion.evidence_from_solution}</p>}
            </article>;
          })}</div>
          {grading.overall_feedback && <div className="model-feedback"><span>ОБРАТНАЯ СВЯЗЬ ИИ</span><p>{grading.overall_feedback}</p></div>}
          <label className="teacher-comment">Комментарий преподавателя<textarea rows={2} disabled={approved} value={grading.teacher_comment ?? ""} onChange={(event) => { setDirty(true); setGrading({ ...grading, teacher_comment: event.target.value }); }} placeholder="Добавьте комментарий студенту…" /></label>
        </> : current.status === "ready_for_review" || current.status === "needs_attention" ? <div className="grading-unavailable"><p>AI-оценка не найдена для этой работы.</p><button className="button secondary" disabled={gradingBusy} onClick={() => void retry()}><RotateCcw size={14} />Повторить оценку</button></div> : null}
        {grading && <footer className="approval-footer"><div><span>ТЕКУЩИЙ БАЛЛ</span><strong>{grading.criteria_results.reduce((sum, item) => sum + (item.teacher_points ?? item.suggested_points), 0)} <small>/ {question?.maximum_points ?? 0}</small></strong></div><div className="footer-actions">{saving && <span className="saving-state"><Save size={13} />Сохраняем</span>}{approved ? <button className="button secondary" onClick={() => void api.reopen(current.id).then(() => load()).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось открыть оценку повторно."))}>Открыть повторно</button> : <button className="button primary approve-button" onClick={() => void approve()} disabled={saving || gradingBusy}>Утвердить и далее <kbd>A</kbd></button>}</div></footer>}
      </div>
    </section>}
    <div className="review-shortcuts"><span><kbd>J</kbd> далее</span><span><kbd>K</kbd> назад</span><span><kbd>A</kbd> утвердить</span><span>ИИ предлагает — преподаватель решает</span></div>
  </AppShell>;
}

function renderMath(text: string) {
  return text.split(/(\$[^$]+\$)/g).map((part, index) => part.startsWith("$") && part.endsWith("$")
    ? <span key={index} dangerouslySetInnerHTML={{ __html: katex.renderToString(part.slice(1, -1), { throwOnError: false }) }} />
    : <span key={index}>{part}</span>);
}

function statusText(status: string) {
  if (status === "awarded") return "Засчитать";
  if (status === "not_awarded") return "Не засчитывать";
  return "Нужна проверка";
}
