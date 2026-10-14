"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { CourseMaterials } from "../../../../components/course-materials";
import { StudentShell } from "../../../../components/student-shell";
import { academicApi, type Offering } from "../../../../lib/academic";

function dueDate(value?: string | null) {
  if (!value) return "Без срока";
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value));
}

export default function StudentCoursePage() {
  const { offeringId } = useParams<{ offeringId: string }>();
  const [offering, setOffering] = useState<Offering | null>(null);
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("due");
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([academicApi.offering(offeringId, "student"), academicApi.studentAssignments()])
      .then(([course, studentAssignments]) => {
        const mine = new Map(studentAssignments.filter((item) => item.offering_id === offeringId).map((item) => [item.id, item]));
        setOffering({ ...course, assignments: course.assignments?.map((item) => ({ ...item, ...mine.get(item.id) })) });
      })
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось загрузить курс."));
  }, [offeringId]);
  const assignments = useMemo(() => {
    const items = (offering?.assignments ?? []).filter((item) => filter === "all" || (item.submission_status ?? "open") === filter);
    return [...items].sort((a, b) => sort === "title" ? a.title.localeCompare(b.title) : String(a.due_at ?? "").localeCompare(String(b.due_at ?? "")));
  }, [offering, filter, sort]);

  return <StudentShell>
    <div className="student-breadcrumb"><Link href="/student">Мои курсы</Link><span>/</span><span>{offering?.code ?? "Курс"} · {offering?.term} {offering?.academic_year}</span></div>
    <div className="student-page-title"><div><div className="eyebrow">{offering?.code} · {offering?.term} {offering?.academic_year}</div><h1>{offering?.course_name ?? offering?.name ?? "Курс"}</h1><p>{offering?.code} · {offering?.term} {offering?.academic_year} · Преподаватель: {offering?.instructor_name ?? offering?.instructor ?? "—"}</p></div></div>
    <nav className="course-tabs"><a className="selected" href="#assignments">Задания</a><Link href="/student/grades">Оценки</Link><a href="#materials">Материалы</a><a href="#information">Информация о курсе</a></nav>
    <div className="student-toolbar"><h2>Задания</h2><div className="student-filters"><label>Статус <select value={filter} onChange={(event) => setFilter(event.target.value)}><option value="all">Все</option><option value="not_started">Не начато</option><option value="submitted">Отправлено</option><option value="graded">Оценено</option><option value="overdue">Просрочено</option></select></label><label>Сортировать <select value={sort} onChange={(event) => setSort(event.target.value)}><option value="due">По сроку</option><option value="title">По названию</option></select></label></div></div>
    {error && <div className="notice error-notice">{error}</div>}
    <div className="student-table-wrap"><table className="student-table assignment-student-table"><thead><tr><th>НАЗВАНИЕ</th><th>ТИП</th><th>ДОСТУПНО С</th><th>СРОК</th><th>СТАТУС ОТПРАВКИ</th><th>ОЦЕНКА</th><th></th></tr></thead><tbody>{assignments.map((item) => <tr key={item.id} className={item.submission_status === "overdue" ? "student-overdue-row" : ""}><td><Link className="student-course-link" href={`/student/assignments/${item.id}`}>{item.title}</Link></td><td>{({ problem_set: "Задачи", essay: "Эссе", lab_report: "Лабораторная", general: "Документ", presentation: "Презентация", research_report: "Проект", programming: "Код" } as Record<string, string>)[item.assignment_type]}</td><td>{dueDate(item.available_at)}</td><td>{dueDate(item.due_at)}</td><td><span className={`student-status status-${item.submission_status ?? item.status}`}>{({ not_started: "Не отправлено", open: "Открыто", submitted: "Отправлено", processing: "Обрабатывается", graded: "Оценено", overdue: "Просрочено", closed: "Закрыто" } as Record<string, string>)[item.submission_status ?? item.status] ?? item.status}</span></td><td>{item.published_at && item.grade !== null && item.grade !== undefined ? `${item.grade} / ${item.maximum_score}` : "—"}</td><td><Link className="student-open-link" href={`/student/assignments/${item.id}`}>{item.submission_status === "submitted" || item.submission_status === "graded" ? "Открыть" : "Перейти"}</Link></td></tr>)}</tbody></table></div>
    {!assignments.length && <div className="student-empty">Для выбранного фильтра заданий нет.</div>}
    <section id="information" className="student-course-information"><h2>Информация о курсе</h2><p>{offering?.course?.department ?? "Учебный курс"} · {offering?.instructor ?? "Преподаватель не указан"} · {offering?.section ?? "Поток"} · {offering?.status === "active" ? "Активный поток" : offering?.status}</p></section>
    <CourseMaterials offeringId={offeringId} />
  </StudentShell>;
}
