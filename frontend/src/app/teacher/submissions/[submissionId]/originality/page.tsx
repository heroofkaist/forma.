"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import { AppShell } from "../../../../../components/app-shell";
import { academicApi, type SimilarityReport } from "../../../../../lib/academic";

const reviews = [["unreviewed", "Оставить без решения"], ["reviewed", "Проверено — действий не требуется"], ["follow_up", "Требуется дальнейшая проверка"]] as const;

export default function OriginalityReportPage() {
  const { submissionId } = useParams<{ submissionId: string }>();
  const [report, setReport] = useState<SimilarityReport | null>(null);
  const [active, setActive] = useState(0);
  const [review, setReview] = useState("unreviewed");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const passageRef = useRef<HTMLSpanElement>(null);
  useEffect(() => { academicApi.originalityReport(submissionId).then((value) => { setReport(value); setReview(value.review_status ?? "reviewed_no_action"); setNotes(value.teacher_notes ?? ""); }).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось загрузить отчёт.")); }, [submissionId]);
  const matches = report?.matches ?? [];
  const currentMatch = matches[active];
  const submittedText = report?.extracted_text ?? "";
  useEffect(() => { passageRef.current?.scrollIntoView({ block: "center", behavior: "smooth" }); }, [active, submittedText]);
  const highlighted = useMemo(() => {
    if (!currentMatch || !submittedText) return <>{submittedText || "В извлечённом документе нет читаемого текста."}</>;
    const start = Math.max(0, Math.min(submittedText.length, currentMatch.current_text_start));
    const end = Math.max(start, Math.min(submittedText.length, currentMatch.current_text_end));
    return <>{submittedText.slice(0, start)}<mark ref={passageRef} className="match-highlight">{submittedText.slice(start, end)}</mark>{submittedText.slice(end)}</>;
  }, [submittedText, currentMatch]);
  function moveMatch(direction: number) {
    if (!matches.length) return;
    const next = Math.max(0, Math.min(matches.length - 1, active + direction));
    setActive(next);
    setReview(matches[next].review_status ?? "unreviewed");
  }
  async function saveReview() {
    if (!report) return;
    try { await academicApi.reviewOriginality(currentMatch?.report_id ?? report.id, { review_status: review, teacher_notes: notes }); setSaved(true); setTimeout(() => setSaved(false), 1800); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось сохранить решение преподавателя."); }
  }
  return <AppShell>
    <div className="breadcrumbs-inline"><Link href="/teacher/originality">Очередь оригинальности</Link><span>/</span><span>{report?.assignment ?? "Отчёт"}</span></div>
    <section className="academic-heading originality-heading"><div><div className="eyebrow">{report?.course ?? "КУРС"} · {report?.assignment ?? "ЗАДАНИЕ"} · {report?.academic_year}</div><h1>Отчёт о совпадениях</h1><p>{report?.document_title ?? report?.student_id ?? "Работа"} · анализ {report?.created_at ? new Date(report.created_at).toLocaleString("ru-RU") : "—"}</p></div><div className="originality-summary"><strong>{Math.round((report?.matched_text_ratio ?? 0) * 100)}%</strong><span>текста совпало<br />в разрешённом архиве</span></div></section>
    {error && <div className="notice error-notice">{error}</div>}
    <div className="academic-info">Доля рассчитывается как число токенов текущего документа, покрытых совпадающими passages, делённое на число допустимых токенов после показанных исключений. Совпадение требует профессиональной оценки и само по себе не является нарушением.</div>
    <div className="originality-meta"><span>Область: {report?.analysis_scope ?? "—"}</span><span>{matches.length} совпадающих фрагментов</span><span>Статус: {report?.analysis_status ?? "—"}</span><span>{report?.eligible_token_count ?? "—"} токенов в сравнении</span></div>
    <div className="originality-split">
      <section className="document-pane"><header><strong>ТЕКУЩАЯ РАБОТА</strong><small>Студент · {report?.academic_year}</small></header><article className="document-text">{highlighted}</article><footer>{currentMatch && <span>Фрагмент {active + 1} из {matches.length}</span>}<div><button className="icon-button" disabled={active <= 0} onClick={() => moveMatch(-1)} aria-label="Предыдущее совпадение"><ChevronLeft size={15} /></button><button className="icon-button" disabled={active >= matches.length - 1} onClick={() => moveMatch(1)} aria-label="Следующее совпадение"><ChevronRight size={15} /></button></div></footer></section>
      <aside className="source-pane"><header><strong>ИСТОЧНИКИ В АРХИВЕ</strong><small>Сначала тот же assignment family</small></header>{matches.length ? <>{matches.map((match, index) => <button className={`source-match ${index === active ? "selected" : ""}`} key={match.id} onClick={() => { setActive(index); setReview(match.review_status ?? "unreviewed"); }}><span className="source-index">{String(index + 1).padStart(2, "0")}</span><span><strong>{match.source_title ?? "Архивная работа"}</strong><small>{match.source_course} · {match.source_term} · {match.source_assignment}</small><small>{match.similarity_method} · фрагмент {index + 1}</small></span><ArrowRight size={14} /></button>)}{currentMatch && <article className="source-excerpt"><div className="eyebrow">СОВПАВШИЙ ФРАГМЕНТ</div><p>{currentMatch.matched_excerpt}</p><small>Текущая позиция {currentMatch.current_text_start}–{currentMatch.current_text_end} · архивная {currentMatch.source_text_start}–{currentMatch.source_text_end}</small></article>}</> : <p className="source-empty">Значимых совпадений в разрешённом архиве не найдено.</p>}
        <div className="exclusion-rules"><strong>ПРАВИЛА ИСКЛЮЧЕНИЯ</strong><ul>{(report?.exclusion_rules ?? ["Короткие общие фразы исключаются.", "Формулы и термины сами по себе не трактуются как авторское заимствование.", "Цитаты и библиография требуют проверки преподавателя."]).map((rule) => <li key={rule}>{rule}</li>)}</ul></div>
      </aside>
    </div>
    <section className="originality-decision"><div><div className="eyebrow">РЕШЕНИЕ ПРЕПОДАВАТЕЛЯ</div><p>Решение сохраняется отдельно от вычисленных метрик и не приводит автоматически к изменению оценки.</p></div><label>Итог проверки<select value={review} onChange={(event) => setReview(event.target.value)}>{reviews.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="academic-description">Заметки преподавателя<textarea rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Зафиксируйте контекст, цитаты или дальнейшие действия…" /></label><button className="button primary" onClick={() => void saveReview()}>{saved ? "Решение сохранено" : "Сохранить проверку"}</button></section>
  </AppShell>;
}
