"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, KeyRound } from "lucide-react";
import { StudentShell } from "../../components/student-shell";
import { academicApi, type Course } from "../../lib/academic";

export default function StudentHomePage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [classCode, setClassCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try { setCourses(await academicApi.courses("student")); setError(""); }
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
    <div className="student-toolbar"><span>{offerings.length} активных курсов</span><form className="enroll-form" onSubmit={(event) => void enroll(event)}><KeyRound size={14} /><input aria-label="Код курса" placeholder="Код курса" value={classCode} onChange={(event) => setClassCode(event.target.value)} /><button type="submit" disabled={!classCode.trim()}>Записаться</button></form></div>
    {error && <div className="notice error-notice">{error}</div>}
    {loading ? <div className="student-loading">Загружаем курсы…</div> : offerings.length ? <div className="student-table-wrap"><table className="student-table"><thead><tr><th>КОД КУРСА</th><th>НАЗВАНИЕ КУРСА</th><th>ПРЕПОДАВАТЕЛЬ</th><th>УЧЕБНЫЙ ПЕРИОД</th><th>ОЖИДАЮТ</th><th>СТАТУС</th><th></th></tr></thead><tbody>{offerings.map(({ course, offering }) => <tr key={offering.id}><td className="student-code">{course.code}</td><td><Link className="student-course-link" href={`/student/courses/${offering.id}`}>{course.name}</Link></td><td>{offering.instructor ?? course.instructor ?? "Преподаватель"}</td><td>{offering.term} {offering.academic_year}</td><td>{offering.pending_assignments ?? 0} заданий</td><td><span className={`student-status ${offering.status === "active" ? "status-open" : "status-archived"}`}>{offering.status === "active" ? "Активен" : offering.status === "archived" ? "Архив" : offering.status}</span></td><td><Link className="student-open-link" href={`/student/courses/${offering.id}`}>Открыть <ArrowRight size={13} /></Link></td></tr>)}</tbody></table></div> : <div className="student-empty"><h2>Пока нет записанных курсов</h2><p>Введите код, который выдал преподаватель, чтобы добавить курс.</p></div>}
  </StudentShell>;
}
