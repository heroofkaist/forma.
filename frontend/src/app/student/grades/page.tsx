"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { StudentShell } from "../../../components/student-shell";
import { academicApi } from "../../../lib/academic";
import { PublishedResult } from "../../../components/published-result";
import type { PublishedGrade } from "../../../lib/published-result";

export default function StudentGradesPage() {
  const [grades, setGrades] = useState<PublishedGrade[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { academicApi.studentGrades().then(setGrades).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось загрузить опубликованные оценки.")); }, []);
  return <StudentShell>
    <div className="student-page-title"><div><div className="eyebrow">МОЁ ОБУЧЕНИЕ</div><h1>Оценки</h1><p>Здесь доступны только оценки, опубликованные преподавателями.</p></div></div>
    {error && <div className="notice error-notice">{error}</div>}
    <div className="student-table-wrap"><table className="student-table grades-table"><thead><tr><th>ЗАДАНИЕ</th><th>ОЦЕНКА</th><th>ОПУБЛИКОВАНО</th></tr></thead><tbody>{grades.map((grade) => <tr key={grade.id}><td><Link className="student-course-link" href={`/student/assignments/${grade.assignment_id}#result`}>{grade.assignment_title}</Link><details><summary>Обратная связь и критерии</summary><PublishedResult grade={grade} /></details></td><td className="student-code">{grade.points} / {grade.maximum_score}</td><td>{grade.published_at ? new Date(grade.published_at).toLocaleDateString("ru-RU") : "—"}</td></tr>)}</tbody></table></div>
    {!grades.length && !error && <div className="student-empty"><h2>Опубликованных оценок пока нет</h2><p>Преподаватель опубликует результат после проверки работы.</p></div>}
  </StudentShell>;
}
