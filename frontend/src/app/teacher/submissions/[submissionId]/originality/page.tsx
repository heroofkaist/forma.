"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import { AppShell } from "../../../../../components/app-shell";
import { academicApi } from "../../../../../lib/academic";

import { codePointPassage, similarityPercent, similarityStates, type SimilarityResult } from "../../../../../lib/similarity";

const reviews = [["unreviewed", "Оставить без решения"], ["reviewed", "Проверено — действий не требуется"], ["follow_up", "Требуется дальнейшая проверка"]] as const;

export default function OriginalityReportPage() {
  const { submissionId } = useParams<{ submissionId: string }>();
  const [result, setResult] = useState<SimilarityResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const report = result?.analysis;
  const [active, setActive] = useState(0);
  const [review, setReview] = useState("unreviewed");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const passageRef = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    let live = true; setLoading(true); setResult(null); setError(""); setActive(0); setSaved(false);
    academicApi.originalityReport(submissionId).then(value => {
      if (!live) return;
      setResult(value); setReview(value.reports[0]?.review_status ?? "unreviewed"); setNotes(value.reports[0]?.teacher_notes ?? "");
    }).catch((cause: unknown) => { if (live) setError(cause instanceof Error ? cause.message : "Не удалось загрузить отчёт."); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [submissionId]);
  const matches = report?.matches ?? [];
  const currentMatch = matches[active];
  const selectedReport = result?.reports.find(r => r.id === currentMatch?.report_id) ?? result?.reports[0];
  const complete = report?.analysis_status === "completed";
  const submittedText = report?.extracted_text ?? "";
  useEffect(() => { passageRef.current?.scrollIntoView({ block: "center", behavior: "smooth" }); }, [active, submittedText]);
  const highlighted = useMemo(() => {
    if (!currentMatch || !submittedText) return <>{submittedText || "В извлечённом документе нет читаемого текста."}</>;
    const [before, passage, after] = codePointPassage(submittedText, currentMatch.current_text_start, currentMatch.current_text_end);
    return <>{before}<mark ref={passageRef} className="match-highlight">{passage}</mark>{after}</>;

  }, [submittedText, currentMatch]);
  function selectMatch(next: number) {
    if (saving || next < 0 || next >= matches.length) return;
    const target = result?.reports.find(r => r.id === matches[next].report_id);
    if (target?.id !== selectedReport?.id && (notes !== (selectedReport?.teacher_notes ?? "") || review !== (selectedReport?.review_status ?? "unreviewed")) && !window.confirm("Перейти к другому источнику без сохранения заметок?")) return;
    setActive(next); setSaved(false); setError("");
    if (target?.id !== selectedReport?.id) { setReview(target?.review_status ?? "unreviewed"); setNotes(target?.teacher_notes ?? ""); }
  }
  async function saveReview() {
    if (!complete || !selectedReport?.id || saving) return;
    setSaving(true); setError(""); setSaved(false);
    try {
      await academicApi.reviewOriginality(selectedReport.id, { review_status: review, teacher_notes: notes });
      setResult(value => value ? {...value, reports: value.reports.map(r => r.id === selectedReport.id ? {...r, review_status: review, teacher_notes: notes} : r)} : value);
      setSaved(true);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось сохранить решение преподавателя."); }
    finally { setSaving(false); }
  }
  return <AppShell>
    <div className="breadcrumbs-inline"><Link href="/teacher/originality">Очередь оригинальности</Link><span>/</span><span>{report?.assignment ?? "Отчёт"}</span></div>
    <section className="academic-heading originality-heading"><div><div className="eyebrow">{report?.course ?? "КУРС"} · {report?.assignment ?? "ЗАДАНИЕ"} · {report?.academic_year}</div><h1>Отчёт о совпадениях</h1><p>{report?.document_title ?? report?.student_id ?? "Работа"} · анализ {report?.created_at ? new Date(report.created_at).toLocaleString("ru-RU") : "—"}</p></div><div className="originality-summary"><strong>{report ? similarityPercent(report) : "—"}</strong><span>{complete ? <>наибольшая доля совпадения<br />с одним источником</> : "Результат недоступен"}</span></div></section>
    {error && <div className="notice error-notice" role="alert">{error}</div>}
    <Link href={`/teacher/submissions/${submissionId}/review`}>К проверке работы →</Link>
    {loading && <p role="status">Загружаем отчёт…</p>}
    {!loading && report && !complete && <div className="academic-info" role="status">{similarityStates[report.analysis_status] ?? similarityStates.incomplete}</div>}
    {complete && <>
    <div className="academic-info">Доля рассчитывается как число токенов текущего документа, покрытых совпадающими фрагментами, делённое на число допустимых токенов в сравниваемом тексте. Совпадение требует профессиональной оценки и само по себе не является нарушением.</div>
    <div className="originality-meta"><span>Область: {report?.analysis_scope ?? "—"}</span><span>{matches.length} совпадающих фрагментов</span><span>Статус: сравнение завершено</span><span>{report?.eligible_token_count ?? "—"} токенов в сравнении</span></div>
    <div className="originality-split">
      <section className="document-pane"><header><strong>ТЕКУЩАЯ РАБОТА</strong><small>Студент · {report?.academic_year}</small></header><article className="document-text">{highlighted}</article><footer>{currentMatch && <span>Фрагмент {active + 1} из {matches.length}</span>}<div><button className="icon-button" disabled={active <= 0} onClick={() => selectMatch(active - 1)} aria-label="Предыдущее совпадение"><ChevronLeft size={15} /></button><button className="icon-button" disabled={active >= matches.length - 1} onClick={() => selectMatch(active + 1)} aria-label="Следующее совпадение"><ChevronRight size={15} /></button></div></footer></section>
      <aside className="source-pane"><header><strong>ИСТОЧНИКИ В АРХИВЕ</strong><small>Источники выбранной области сравнения</small></header>{matches.length ? <>{matches.map((match, index) => <button className={`source-match ${index === active ? "selected" : ""}`} key={match.id} onClick={() => selectMatch(index)}><span className="source-index">{String(index + 1).padStart(2, "0")}</span><span><strong>{match.source_title ?? "Архивная работа"}</strong><small>{match.source_course} · {match.source_term} · {match.source_assignment}</small><small>{match.similarity_method} · фрагмент {index + 1}</small></span><ArrowRight size={14} /></button>)}{currentMatch && <article className="source-excerpt"><div className="eyebrow">СОВПАВШИЙ ФРАГМЕНТ</div><p>{currentMatch.matched_excerpt}</p><p>{selectedReport && <>С этим источником: {similarityPercent(selectedReport)} · </>}<Link href={`/teacher/submissions/${currentMatch.source_submission_id}/review`}>Открыть источник →</Link></p><small>Текущая позиция {currentMatch.current_text_start}–{currentMatch.current_text_end} · архивная {currentMatch.source_text_start}–{currentMatch.source_text_end}</small></article>}</> : <p className="source-empty">В проверенных источниках не найдено последовательностей из 8 и более совпадающих слов. Это не вывод об авторстве работы.</p>}
        <div className="exclusion-rules"><strong>ПРАВИЛА ИСКЛЮЧЕНИЯ</strong><ul>{(report?.exclusion_rules ?? ["Короткие общие фразы исключаются.", "Сравниваются последовательности слов без учёта регистра.", "Цитаты, формулы и библиография автоматически не исключаются; их контекст оценивает преподаватель."]).map((rule) => <li key={rule}>{rule}</li>)}</ul></div>
      </aside>
    </div>
    {selectedReport?.id && <section className="originality-decision"><div><div className="eyebrow">РЕШЕНИЕ ПРЕПОДАВАТЕЛЯ</div><p>Решение сохраняется отдельно от вычисленных метрик и не приводит автоматически к изменению оценки.</p></div><label>Итог проверки<select value={review} onChange={(event) => setReview(event.target.value)}>{reviews.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="academic-description">Заметки преподавателя<textarea rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Зафиксируйте контекст, цитаты или дальнейшие действия…" /></label><button className="button primary" disabled={saving} onClick={() => void saveReview()}>{saved ? "Решение сохранено" : saving ? "Сохраняем…" : "Сохранить проверку"}</button></section>}
    </>}
  </AppShell>;
}
