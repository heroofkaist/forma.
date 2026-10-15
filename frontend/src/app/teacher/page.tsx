"use client";

import { termLabel } from "../../lib/presentation";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { platformRequest } from "../../lib/platform";
import { useAuth } from "../../components/auth-provider";
import { AppShell } from "../../components/app-shell";
import { academicApi, type Course, type Offering } from "../../lib/academic";

export default function TeacherHomePage() {
  const { enabled, user } = useAuth();
  const [queue, setQueue] = useState<{ id: string; assignment_title: string; student_name: string; submitted_at: string }[]>([]);
  const [offerings, setOfferings] = useState<Offering[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ course_id: "", academic_year: "2026", term: "Fall", section: "01" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  async function load() {
    setLoading(true);
    try {
      const [items, courseItems] = await Promise.all([academicApi.offerings(), academicApi.courses("teacher")]);
      setOfferings(items);
      if (enabled) {
        const overview = await platformRequest<{ review_queue: typeof queue }>("/api/teacher-overview");
        setQueue(overview.review_queue);
      }
      setCourses(courseItems);
      setForm((current) => ({ ...current, course_id: current.course_id || courseItems[0]?.id || "" }));
      setError("");
    }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось загрузить учебные курсы."); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, [enabled]);
  async function createOffering(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try { await academicApi.createOffering(form); setShowForm(false); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось создать учебный поток."); }
  }
  return <AppShell>
    <div className="academic-crumb">FORMA <span>/</span> ПРЕПОДАВАТЕЛЬ</div>
    <section className="academic-heading"><div><div className="eyebrow">ПРЕПОДАВАТЕЛЬ · КУРСЫ</div><h1>Учебные потоки</h1><p>Курсы, задания и архивные работы сгруппированы по учебным годам.</p></div><Link className="button" href="/teacher/courses/new">Создать курс</Link><button className="button primary" onClick={() => setShowForm(!showForm)}><Plus size={14} />Новый поток</button></section>
    {!enabled && <div className="academic-info">ДЕМО · синтетические данные.</div>}
    {error && <div className="notice error-notice">{error}</div>}
    {showForm && <form className="academic-form-grid" onSubmit={(event) => void createOffering(event)}><label>Курс<select value={form.course_id} required onChange={(event) => setForm({ ...form, course_id: event.target.value })}>{courses.map((course) => <option key={course.id} value={course.id}>{course.code} · {course.name}</option>)}</select></label><label>Год<input type="number" value={form.academic_year} required onChange={(event) => setForm({ ...form, academic_year: event.target.value })} /></label><label>Семестр<select value={form.term} onChange={(event) => setForm({ ...form, term: event.target.value })}><option value="Fall">Осень</option><option value="Spring">Весна</option><option value="Summer">Лето</option></select></label><label>Группа<input value={form.section} onChange={(event) => setForm({ ...form, section: event.target.value })} /></label><button className="button primary" type="submit" disabled={!courses.length}>Создать поток</button></form>}

    <div className="academic-section-header"><strong>КУРСЫ И ПОТОКИ</strong><span>{offerings.length} потоков</span></div>
    {loading ? <div className="student-loading">Загружаем потоки…</div> : offerings.length ? <div className="course-index">{offerings.map((item, index) => <article className="course-sheet" key={item.id}><div className="course-sheet-register"><span>ПОТОК / {String(index + 1).padStart(2, "0")}</span><span>{termLabel(item.term)} {item.academic_year}</span></div><div className="course-sheet-title"><span className="course-sheet-symbol" aria-hidden="true">{index % 2 ? "↗" : "+"}</span><div><span className="course-sheet-code">{item.code}</span><h2><Link href={`/teacher/courses/${item.id}/assignments`}>{item.course_name ?? item.name}</Link></h2></div></div><dl className="course-sheet-facts"><div><dt>Группа</dt><dd>{item.section ?? "—"}</dd></div><div><dt>Студенты</dt><dd>{item.enrollment_count ?? "—"}</dd></div><div><dt>Задания</dt><dd>{item.assignment_count ?? item.assignments?.length ?? 0}</dd></div></dl><div className="course-sheet-access"><span>КОД ЗАПИСИ <strong>{item.class_code ?? "—"}</strong></span>{Boolean(user?.account_id) && <Link href={`/teacher/courses/${item.id}/students`}>Студенты ↗</Link>}</div><Link className="course-sheet-open" href={`/teacher/courses/${item.id}/assignments`}>Открыть поток<span aria-hidden="true">↗</span></Link></article>)}</div> : <div className="student-empty"><h2>Учебные потоки пока не созданы</h2><p>Создайте курс, затем пригласите студентов по коду.</p></div>}
    {enabled && <section className="platform-panel"><div className="academic-section-header"><strong>ОЖИДАЮТ ПРОВЕРКИ</strong><span>{queue.length}</span></div>{queue.length ? <div className="student-table-wrap"><table className="student-table"><thead><tr><th>ЗАДАНИЕ</th><th>СТУДЕНТ</th><th>ОТПРАВЛЕНО</th><th></th></tr></thead><tbody>{queue.slice(0, 10).map((item) => <tr key={item.id}><td>{item.assignment_title}</td><td>{item.student_name}</td><td>{new Date(item.submitted_at).toLocaleDateString("ru-RU")}</td><td><Link href={`/teacher/submissions/${item.id}/review`}>Проверить →</Link></td></tr>)}</tbody></table></div> : <p>Нет работ, ожидающих проверки.</p>}</section>}
  </AppShell>;
}
