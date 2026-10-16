"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Search, X } from "lucide-react";
import { StudentShell } from "../../components/student-shell";
import { CourseEnrollment } from "../../components/course-enrollment";
import { academicApi, type Course, type AcademicAssignment } from "../../lib/academic";
import { statusLabel, termLabel } from "../../lib/presentation";
import { dashboardWork, searchCourses, taskCount, workFilters, workState, type WorkFilter } from "../../lib/student-dashboard";

export default function StudentHomePage() {
  const [work, setWork] = useState<AcademicAssignment[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<WorkFilter>("all");
  const [visible, setVisible] = useState(10);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true); setError("");
    try {
      const [items, assignments] = await Promise.all([academicApi.courses("student"), academicApi.studentAssignments()]);
      setCourses(items); setWork(assignments); setVisible(10);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось загрузить курсы."); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);
  const allOfferings = searchCourses(courses, "");
  const offerings = searchCourses(courses, search);
  const assignments = dashboardWork(work, filter);
  const pending = dashboardWork(work, "todo");

  return <StudentShell>
    <div className="student-page-title"><div><div className="eyebrow">УЧЕБНОЕ ПРОСТРАНСТВО</div><h1>Мои курсы</h1><p>Ваши курсы, ближайшие задания и результаты — в одном месте.</p></div></div>
    <CourseEnrollment onJoined={load}/>
    {error && <div className="notice error-notice" role="alert"><span>{error}</span><button className="button" onClick={() => void load()}>Попробовать снова</button></div>}
    {loading ? <div className="student-loading" role="status">Загружаем курсы…</div> : !error && <>
      <div className="student-course-tools">
        <p aria-live="polite">Курсов: <strong>{allOfferings.length}</strong> · активных: {allOfferings.filter(({offering}) => offering.status === "active").length}{search.trim() && <> · найдено: {offerings.length}</>}</p>
        <div className="course-search"><Search size={17} aria-hidden="true"/><input aria-label="Поиск по моим курсам" placeholder="Курс, код или преподаватель" value={search} onChange={event => setSearch(event.target.value)}/>{search && <button type="button" onClick={() => setSearch("")} aria-label="Очистить поиск"><X size={17}/></button>}</div>
      </div>
      {offerings.length ? <div className="course-index student-course-index">{offerings.map(({ course, offering }, index) => {
        const next = pending.find(item => item.offering_id === offering.id);
        return <article className="course-sheet" key={offering.id}>
          <div className="course-sheet-register"><span>КУРС / {String(index + 1).padStart(2, "0")}</span><span>{termLabel(offering.term)} {offering.academic_year}</span></div>
          <div className="course-sheet-title"><span className="course-sheet-symbol" aria-hidden="true">{index % 2 ? "↗" : "+"}</span><div><span className="course-sheet-code">{course.code}</span><h2><Link href={`/student/courses/${offering.id}`}>{course.name}</Link></h2></div></div>
          <p className="course-sheet-instructor">{offering.instructor ?? course.instructor ?? "Преподаватель"}</p>
          {next && offering.status === "active" && <Link className="course-next-task" href={`/student/assignments/${next.id}`}><span>СЛЕДУЮЩИЙ ШАГ</span><strong>{next.title}</strong><ArrowRight size={16} aria-hidden="true"/></Link>}
          <div className="course-sheet-access"><span>ОЖИДАЮТ <strong>{taskCount(offering.pending_assignments ?? 0)}</strong></span><span className={`student-status ${offering.status === "active" ? "status-open" : "status-archived"}`}>{offering.status === "active" ? "Активен" : offering.status === "archived" ? "Архив" : statusLabel(offering.status)}</span></div>
          <Link className="course-sheet-open" href={`/student/courses/${offering.id}`}>Открыть курс<ArrowRight size={22}/></Link>
        </article>;
      })}</div> : <div className="student-empty"><h2>{search.trim() ? "Курсы не найдены" : "Пока нет записанных курсов"}</h2><p>{search.trim() ? "Попробуйте другое название, код или имя преподавателя." : "Введите код от преподавателя в форму выше, чтобы добавить первый курс."}</p>{search.trim() && <button className="button" onClick={() => setSearch("")}>Сбросить поиск</button>}</div>}
      <section className="platform-panel student-work-panel" aria-labelledby="student-work-title">
        <div className="student-work-heading"><div><div className="eyebrow">ВАША РАБОЧАЯ ОЧЕРЕДЬ</div><h2 id="student-work-title">Задания и результаты</h2></div><span>{taskCount(work.length)}</span></div>
        <div className="student-work-filters" role="group" aria-label="Фильтр заданий">{workFilters.map(option => <button className="button" key={option.value} aria-pressed={filter === option.value} onClick={() => {setFilter(option.value); setVisible(10);}}>{option.label}<span>{option.value === "all" ? work.length : work.filter(item => workState(item) === option.value).length}</span></button>)}</div>
        {assignments.length ? <><div className="student-table-wrap"><table className="student-table"><thead><tr><th>ЗАДАНИЕ</th><th>СРОК</th><th>СТАТУС</th><th>ОЦЕНКА</th></tr></thead><tbody>{assignments.slice(0, visible).map(item => <tr key={item.id}><td><Link href={`/student/assignments/${item.id}`}>{item.title}</Link></td><td>{item.due_at && Number.isFinite(Date.parse(item.due_at)) ? new Date(item.due_at).toLocaleString("ru-RU") : "Без срока"}</td><td>{workState(item) === "graded" ? "Оценка опубликована" : workState(item) === "submitted" ? "Ожидает проверки" : item.submission_status === "overdue" ? "Просрочено" : "Ожидает отправки"}</td><td>{item.published_at && item.grade != null ? `${item.grade} / ${item.maximum_score}` : "—"}</td></tr>)}</tbody></table></div>{assignments.length > visible && <button className="button student-show-more" onClick={() => setVisible(count => count + 10)}>Показать ещё · осталось {assignments.length - visible}</button>}</> : <p className="student-work-empty" role="status">{work.length ? "В этой категории пока нет заданий." : "Когда преподаватель опубликует задания, они появятся здесь."}</p>}
      </section>
    </>}
  </StudentShell>;
}
