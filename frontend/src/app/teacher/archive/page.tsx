"use client";

import { FormEvent, useState } from "react";
import { Search } from "lucide-react";
import { AppShell } from "../../../components/app-shell";
import { academicApi, type ArchiveSubmission } from "../../../lib/academic";

export default function TeacherArchivePage() {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<ArchiveSubmission[]>([]);
  const [error, setError] = useState("");
  const [searched, setSearched] = useState(false);
  async function search(event: FormEvent) {
    event.preventDefault();
    try { setItems(await academicApi.archive(query)); setSearched(true); setError(""); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось выполнить поиск по архиву."); }
  }
  return <AppShell>
    <div className="academic-crumb">FORMA <span>/</span> АРХИВ</div>
    <section className="academic-heading"><div><div className="eyebrow">ИСТОРИЧЕСКИЙ АРХИВ</div><h1>Работы прошлых потоков</h1><p>Поиск по разрешённым материалам. Доступ к архивным файлам в этом демо намеренно закрыт.</p></div></section>
    <div className="academic-info">Архивные документы содержат учебные записи и авторские работы. Реальные сроки хранения, основания доступа и удаление должны определяться политикой учреждения.</div>
    <form className="archive-search" onSubmit={(event) => void search(event)}><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Курс, учебный год, задание или тип документа" /><button className="button secondary">Искать в архиве</button></form>
    {error && <div className="notice error-notice">{error}</div>}
    {searched && items.length ? <div className="academic-originality-table"><div className="academic-originality-row academic-table-head"><span>РАБОТА</span><span>КУРС</span><span>УЧЕБНЫЙ ГОД</span><span>ЗАДАНИЕ</span><span>ДОКУМЕНТ</span><span>ОТПРАВЛЕНО</span><span>ФРАГМЕНТ</span></div>{items.map((item) => <div className="academic-originality-row" key={item.submission_id}><strong>{item.student_id}</strong><span>{item.course_code} · {item.course_name}</span><span>{item.academic_year} · {item.term}</span><span>{item.assignment_title}</span><span>{item.file_name} <small>{item.file_type.toUpperCase()}</small></span><span>{item.submitted_at ? new Date(item.submitted_at).toLocaleDateString("ru-RU") : "—"}</span><details><summary>Текст</summary><p>{item.extracted_text.slice(0, 500)}{item.extracted_text.length > 500 ? "…" : ""}</p></details></div>)}</div> : searched ? <div className="student-empty">В доступном архиве ничего не найдено.</div> : <div className="archive-empty"><strong>Архив разделён по курсам и учебным годам</strong><p>При анализе новых работ сначала проверяется семейство того же задания, затем при разрешении — работы того же курса.</p></div>}
  </AppShell>;
}
