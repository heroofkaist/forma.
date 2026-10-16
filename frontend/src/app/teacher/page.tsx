"use client";

import { termLabel } from "../../lib/presentation";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, BookOpen, ClipboardCheck, Plus, Search, X } from "lucide-react";
import { platformRequest } from "../../lib/platform";
import { useAuth } from "../../components/auth-provider";
import { AppShell } from "../../components/app-shell";
import { academicApi, type Course, type Offering } from "../../lib/academic";

type QueueItem = { id: string; assignment_title: string; student_name: string; submitted_at: string };
export default function TeacherHomePage() {
  const { enabled, user } = useAuth();
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [offerings, setOfferings] = useState<Offering[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [query, setQuery] = useState("");
  const [form, setForm] = useState({ course_id: "", academic_year: String(new Date().getFullYear()), term: "Fall", section: "01" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const creatingRef = useRef(false);
  async function load() {
    setLoading(true);
    try {
      const [items, courseItems, overview] = await Promise.all([academicApi.offerings(), academicApi.courses("teacher"), enabled ? platformRequest<{ review_queue: QueueItem[] }>("/api/teacher-overview") : Promise.resolve({ review_queue: [] })]);
      setOfferings(items); setCourses(courseItems); setQueue(overview.review_queue);
      setForm(current => ({ ...current, course_id: current.course_id || courseItems[0]?.id || "" }));
      setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось загрузить курсы. Попробуйте ещё раз."); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, [enabled]);
  async function createOffering(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (creatingRef.current) return;
    creatingRef.current = true; setCreating(true); setError("");
    try { await academicApi.createOffering(form); setShowForm(false); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось создать поток. Заполненные поля сохранены."); }
    finally { creatingRef.current = false; setCreating(false); }
  }
  const visible = offerings.filter(item => `${item.course_name ?? item.name} ${item.code} ${item.section ?? ""} ${item.academic_year}`.toLocaleLowerCase("ru").includes(query.trim().toLocaleLowerCase("ru")));
  return <AppShell>
    <section className="academic-heading teacher-home-heading"><div><div className="eyebrow">ВАШЕ УЧЕБНОЕ ПРОСТРАНСТВО</div><h1>Мои курсы</h1><p>Задания, студенты и результаты каждого потока.</p></div><div className="heading-actions"><Link className="button" href="/teacher/courses/new">Создать курс</Link><button className="button primary" aria-expanded={showForm} aria-controls="new-offering-form" onClick={() => setShowForm(!showForm)}><Plus size={17} aria-hidden="true"/>Новый поток</button></div></section>
    {!enabled && <div className="academic-info">Демо-пространство · все данные вымышлены.</div>}
    {error && <div className="notice error-notice" role="alert"><span>{error}</span><button className="button" onClick={() => void load()}>Повторить загрузку</button></div>}
    {showForm && <section id="new-offering-form" className="new-offering-panel"><div className="assignment-section-heading"><div><h2>Новый учебный поток</h2><p>Выберите курс и укажите, какая группа будет его проходить.</p></div><button className="quiet-button" disabled={creating} onClick={() => setShowForm(false)}>Отменить</button></div>{courses.length ? <form className="academic-form-grid" onSubmit={event => void createOffering(event)} aria-busy={creating}><label>Курс<select value={form.course_id} required disabled={creating} onChange={event => setForm({ ...form, course_id: event.target.value })}>{courses.map(course => <option key={course.id} value={course.id}>{course.code} · {course.name}</option>)}</select></label><label>Учебный год<input type="number" min="2000" max="2200" value={form.academic_year} required disabled={creating} onChange={event => setForm({ ...form, academic_year: event.target.value })}/></label><label>Семестр<select value={form.term} disabled={creating} onChange={event => setForm({ ...form, term: event.target.value })}><option value="Fall">Осень</option><option value="Spring">Весна</option><option value="Summer">Лето</option></select></label><label>Группа<input value={form.section} required disabled={creating} onChange={event => setForm({ ...form, section: event.target.value })}/></label><button className="button primary" type="submit" disabled={creating}>{creating ? "Создаём поток…" : "Создать поток"}</button></form> : <p>Сначала <Link className="inline-link" href="/teacher/courses/new">создайте курс</Link>, затем добавьте для него поток.</p>}</section>}
    {enabled && !loading && !error && <section className="teacher-next-step" aria-labelledby="next-step-title"><span className="next-step-icon" aria-hidden="true"><ClipboardCheck size={24}/></span><div><span className="eyebrow">СЛЕДУЮЩИЙ ШАГ</span><h2 id="next-step-title">{queue.length ? "Работы ждут вашей проверки" : "Все работы проверены"}</h2><p>{queue.length ? `В очереди: ${queue.length}. Откройте работу, проверьте критерии и опубликуйте оценку.` : "Новые работы появятся в очереди после отправки студентами."}</p></div>{queue.length > 0 && <Link className="button primary" href={`/teacher/submissions/${queue[0].id}/review`}>Начать проверку<ArrowRight size={17} aria-hidden="true"/></Link>}<Link className="inline-link" href="/teacher/review">Вся очередь</Link></section>}
    <div className="course-collection-heading"><div><h2>Курсы и потоки</h2><span role="status">{loading ? "Загружаем…" : `Показано: ${visible.length} из ${offerings.length}`}</span></div><label className="course-search"><Search size={18} aria-hidden="true"/><input type="search" aria-label="Поиск по курсам и потокам" placeholder="Название, код, группа или год" value={query} onChange={event => setQuery(event.target.value)}/>{query && <button type="button" onClick={() => setQuery("")} aria-label="Очистить поиск"><X size={17}/></button>}</label></div>
    {loading ? <div className="student-loading" role="status">Загружаем курсы…</div> : visible.length ? <div className="course-index">{visible.map(item => <article className="course-sheet" key={item.id}><div className="course-sheet-register"><span>{item.code}</span><span>{termLabel(item.term)} {item.academic_year}</span></div><div className="course-sheet-title"><span className="course-sheet-symbol" aria-hidden="true"><BookOpen size={24}/></span><div><span className="course-sheet-code">Группа {item.section || "не указана"}</span><h2><Link href={`/teacher/courses/${item.id}/assignments`}>{item.course_name ?? item.name}</Link></h2></div></div><dl className="course-sheet-facts"><div><dt>Студенты</dt><dd>{item.enrollment_count ?? "—"}</dd></div><div><dt>Задания</dt><dd>{item.assignment_count ?? item.assignments?.length ?? 0}</dd></div><div><dt>Код записи</dt><dd className="course-access-code">{item.class_code ?? "—"}</dd></div></dl><div className="course-sheet-access"><Link href={`/teacher/courses/${item.id}/assignments`}>Задания и работы<ArrowRight size={16} aria-hidden="true"/></Link>{Boolean(user?.account_id) && <Link href={`/teacher/courses/${item.id}/students`}>Студенты</Link>}</div></article>)}</div> : <div className="student-empty"><BookOpen size={28} aria-hidden="true"/><h2>{query ? "Курсы не найдены" : "Здесь будут ваши курсы"}</h2><p>{query ? "Попробуйте другое название, код или учебный год." : "Создайте курс и добавьте учебный поток. Студенты смогут присоединиться по коду."}</p>{query ? <button className="button" onClick={() => setQuery("")}>Сбросить поиск</button> : <Link className="button primary" href="/teacher/courses/new">Создать первый курс</Link>}</div>}
    {enabled && queue.length > 0 && <section className="platform-panel"><div className="assignment-section-heading"><div><h2>Последние работы в очереди</h2><p>До публикации предварительные баллы видны только вам.</p></div><Link className="inline-link" href="/teacher/review">Все работы<ArrowRight size={16} aria-hidden="true"/></Link></div><div className="teacher-queue-preview">{queue.slice(0, 4).map(item => <Link href={`/teacher/submissions/${item.id}/review`} key={item.id}><span className="queue-avatar" aria-hidden="true">{item.student_name.slice(0, 1)}</span><span><strong>{item.student_name}</strong><small>{item.assignment_title}</small></span><span className="queue-open">Проверить<ArrowRight size={16} aria-hidden="true"/></span></Link>)}</div></section>}
  </AppShell>;
}
