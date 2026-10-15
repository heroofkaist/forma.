"use client";
import { statusLabel } from "../../../lib/presentation";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { AppShell } from "../../../components/app-shell";
import { academicApi, type SimilarityReport } from "../../../lib/academic";

import { similarityPercent, similarityStates } from "../../../lib/similarity";

const statusNames: Record<string, string> = { pending: "Ожидает анализа", analyzing: "Анализируется", ready: "К проверке", unreviewed: "К проверке", reviewed: "Проверено", follow_up: "Требуется проверка", needs_investigation: "Нужно внимание", failed: "Ошибка анализа" };

export default function TeacherOriginalityQueuePage() {
  const [loading, setLoading] = useState(true);
  const [reports, setReports] = useState<SimilarityReport[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [error, setError] = useState("");
  useEffect(() => { academicApi.originalityQueue().then(setReports).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось загрузить очередь оригинальности.")).finally(() => setLoading(false)); }, []);
  const visible = useMemo(() => reports.filter((report) => {
    const text = `${report.course ?? ""} ${report.assignment ?? ""} ${report.document_title ?? ""} ${report.academic_year ?? ""}`.toLowerCase();
    return (!query || text.includes(query.toLowerCase())) && (status === "all" || report.analysis_status === status || report.review_status === status);
  }).sort((a, b) => (b.matched_text_ratio ?? -1) - (a.matched_text_ratio ?? -1)), [reports, query, status]);
  return <AppShell>
    <div className="academic-crumb">FORMA <span>/</span> ОРИГИНАЛЬНОСТЬ</div>
    <section className="academic-heading"><div><div className="eyebrow">АРХИВ · РУЧНАЯ ПРОВЕРКА</div><h1>Проверка оригинальности</h1><p>Детерминированное сравнение текстов с разрешённым историческим архивом. Совпадение — не вывод о нарушении.</p></div></section>
    <div className="academic-info">Процент показывает долю токенов текста, совпавших с доступными архивными источниками после правил исключения. Это не вероятность заимствования.</div>
    {error && <div className="notice error-notice">{error}</div>}
    <div className="academic-queue-toolbar"><label className="search-field"><Search size={14} /><input placeholder="Курс, задание или учебный год" value={query} onChange={(event) => setQuery(event.target.value)} /></label><label>Статус <select value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">Все</option><option value="unreviewed">К проверке</option><option value="reviewed">Проверено</option><option value="follow_up">Требуется проверка</option></select></label></div>
    <div className="academic-originality-table"><div className="academic-originality-row academic-table-head"><span>РАБОТА</span><span>КУРС · ЗАДАНИЕ</span><span>ОТПРАВЛЕНО</span><span>СОВПАВШИЙ ТЕКСТ</span><span>ИСТОЧНИКИ</span><span>СТАТУС</span><span></span></div>{visible.map((report) => <div className="academic-originality-row" key={report.id}><strong>{report.document_title ?? report.student_id ?? "Работа"}</strong><span>{report.course ?? "Курс"} · {report.assignment ?? "Задание"}<small>{report.academic_year}</small></span><span>{report.created_at ? new Date(report.created_at).toLocaleString("ru-RU") : "—"}</span><strong className="ratio-value">{similarityPercent(report)}</strong><span>{report.analysis_status === "completed" ? `${report.matches.length} совпадений` : "—"}</span><span className="student-status">{report.analysis_status === "completed" ? statusNames[report.review_status ?? "unreviewed"] : similarityStates[report.analysis_status] ?? statusLabel(report.analysis_status)}</span><Link className="student-open-link" href={`/teacher/submissions/${report.submission_id}/originality`}>Открыть →</Link></div>)}</div>
    {loading && <p role="status">Загружаем отчёты…</p>}
    {!loading && !visible.length && !error && <div className="student-empty"><h2>В очереди нет отчётов</h2><p>Здесь отображаются сохранённые сравнения с архивными источниками. Отсутствие отчётов не означает отсутствие совпадений.</p></div>}
  </AppShell>;
}
