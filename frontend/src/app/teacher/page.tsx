"use client";

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
    {showForm && <form className="academic-form-grid" onSubmit={(event) => void createOffering(event)}><label>Курс<select value={form.course_id} required onChange={(event) => setForm({ ...form, course_id: event.target.value })}>{courses.map((course) => <option key={course.id} value={course.id}>{course.code} · {course.name}</option>)}</select></label><label>Год<input type="number" value={form.academic_year} required onChange={(event) => setForm({ ...form, academic_year: event.target.value })} /></label><label>Семестр<select value={form.term} onChange={(event) => setForm({ ...form, term: event.target.value })}><option>Fall</option><option>Spring</option><option>Summer</option></select></label><label>Группа<input value={form.section} onChange={(event) => setForm({ ...form, section: event.target.value })} /></label><button className="button primary" type="submit" disabled={!courses.length}>Создать поток</button></form>}
    {enabled && <section className="platform-panel"><div className="academic-section-header"><strong>ОЖИДАЮТ ПРОВЕРКИ</strong><span>{queue.length}</span></div>{queue.length ? <div className="student-table-wrap"><table className="student-table"><thead><tr><th>ЗАДАНИЕ</th><th>СТУДЕНТ</th><th>ОТПРАВЛЕНО</th><th></th></tr></thead><tbody>{queue.slice(0, 10).map((item) => <tr key={item.id}><td>{item.assignment_title}</td><td>{item.student_name}</td><td>{new Date(item.submitted_at).toLocaleDateString("ru-RU")}</td><td><Link href={`/teacher/submissions/${item.id}/review`}>Проверить →</Link></td></tr>)}</tbody></table></div> : <p>Нет работ, ожидающих проверки.</p>}</section>}
    <div className="academic-section-header"><strong>КУРСЫ И ПОТОКИ</strong><span>{offerings.length} потоков</span></div>
    {loading ? <div className="student-loading">Загружаем потоки…</div> : offerings.length ? <div className="academic-offering-table"><div className="academic-offering-row academic-table-head"><span>КУРС</span><span>УЧЕБНЫЙ ГОД</span><span>ГРУППА</span><span>СТУДЕНТЫ</span><span>ЗАДАНИЯ</span><span>КОД ЗАПИСИ</span><span></span></div>{offerings.map((item) => <div className="academic-offering-row" key={item.id}><span><strong>{item.code}</strong><small>{item.course_name ?? item.name}</small></span><span>{item.term} {item.academic_year}</span><span>{item.section ?? "—"}</span><span>{item.enrollment_count ?? "—"}</span><span>{item.assignment_count ?? item.assignments?.length ?? 0}</span><span className="academic-class-code">{item.class_code ?? "—"}</span><div className="academic-row-actions"><Link className="student-open-link" href={`/teacher/courses/${item.id}/assignments`}>Открыть →</Link>{Boolean(user?.account_id) && <Link href={`/teacher/courses/${item.id}/students`}>Студенты</Link>}</div></div>)}</div> : <div className="student-empty"><h2>Учебные потоки пока не созданы</h2><p>Создайте курс, затем пригласите студентов по коду.</p></div>}
  </AppShell>;
}
