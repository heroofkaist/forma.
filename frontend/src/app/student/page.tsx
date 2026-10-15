"use client";
import { statusLabel, termLabel } from "../../lib/presentation";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, KeyRound } from "lucide-react";
import { StudentShell } from "../../components/student-shell";
import { academicApi, type Course, type AcademicAssignment } from "../../lib/academic";

export default function StudentHomePage() {
  const [work, setWork] = useState<AcademicAssignment[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [classCode, setClassCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try { const [items, assignments] = await Promise.all([academicApi.courses("student"), academicApi.studentAssignments()]); setCourses(items); setWork(assignments); setError(""); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось загрузить курсы."); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);
  async function enroll(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try { await academicApi.enroll(classCode.trim()); setClassCode(""); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось записаться на курс."); }
  }

  const offerings = courses.flatMap((course) => course.offerings.map((offering) => ({ course, offering })));
  return <StudentShell>
    <div className="student-page-title"><div><div className="eyebrow">УЧЕБНОЕ ПРОСТРАНСТВО</div><h1>Мои курсы</h1><p>Курсы, на которые вы записаны в этом семестре.</p></div></div>
    <div className="student-toolbar"><Link className="button" href="/student/join">Вступить в курс</Link><span>{offerings.length} активных курсов</span><form className="enroll-form" onSubmit={(event) => void enroll(event)}><KeyRound size={14} /><input aria-label="Код курса" placeholder="Код курса" value={classCode} onChange={(event) => setClassCode(event.target.value)} /><button type="submit" disabled={!classCode.trim()}>Записаться</button></form></div>
    {error && <div className="notice error-notice">{error}</div>}
    {loading ? <div className="student-loading">Загружаем курсы…</div> : offerings.length ? <div className="course-index student-course-index">{offerings.map(({ course, offering }, index) => <article className="course-sheet" key={offering.id}><div className="course-sheet-register"><span>КУРС / {String(index + 1).padStart(2, "0")}</span><span>{termLabel(offering.term)} {offering.academic_year}</span></div><div className="course-sheet-title"><span className="course-sheet-symbol" aria-hidden="true">{index % 2 ? "↗" : "+"}</span><div><span className="course-sheet-code">{course.code}</span><h2><Link href={`/student/courses/${offering.id}`}>{course.name}</Link></h2></div></div><p className="course-sheet-instructor">{offering.instructor ?? course.instructor ?? "Преподаватель"}</p><div className="course-sheet-access"><span>ОЖИДАЮТ <strong>{offering.pending_assignments ?? 0} заданий</strong></span><span className={`student-status ${offering.status === "active" ? "status-open" : "status-archived"}`}>{offering.status === "active" ? "Активен" : offering.status === "archived" ? "Архив" : statusLabel(offering.status)}</span></div><Link className="course-sheet-open" href={`/student/courses/${offering.id}`}>Открыть курс<ArrowRight size={22}/></Link></article>)}</div> : <div className="student-empty"><h2>Пока нет записанных курсов</h2><p>Введите код, который выдал преподаватель, чтобы добавить курс.</p></div>}
    {!loading && work.length > 0 && <section className="platform-panel"><h2>Ближайшие задания и результаты</h2><div className="student-table-wrap"><table className="student-table"><thead><tr><th>ЗАДАНИЕ</th><th>СРОК</th><th>СТАТУС</th><th>ОЦЕНКА</th></tr></thead><tbody>{[...work].sort((a, b) => String(a.due_at ?? "9999").localeCompare(String(b.due_at ?? "9999"))).slice(0, 10).map((item) => <tr key={item.id}><td><Link href={`/student/assignments/${item.id}`}>{item.title}</Link></td><td>{item.due_at ? new Date(item.due_at).toLocaleString("ru-RU") : "Без срока"}</td><td>{item.submission_status === "graded" ? "Оценка опубликована" : item.submission_status === "submitted" ? "Ожидает проверки" : item.submission_status === "overdue" ? "Просрочено" : "Ожидает отправки"}</td><td>{item.published_at ? `${item.grade} / ${item.maximum_score}` : "—"}</td></tr>)}</tbody></table></div></section>}
  </StudentShell>;
}
