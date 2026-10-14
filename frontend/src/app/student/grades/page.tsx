"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { StudentShell } from "../../../components/student-shell";
import { academicApi } from "../../../lib/academic";

export default function StudentGradesPage() {
  const [grades, setGrades] = useState<Record<string, unknown>[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { academicApi.studentGrades().then(setGrades).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось загрузить опубликованные оценки.")); }, []);
  return <StudentShell>
    <div className="student-page-title"><div><div className="eyebrow">МОЁ ОБУЧЕНИЕ</div><h1>Оценки</h1><p>Здесь доступны только оценки, опубликованные преподавателями.</p></div></div>
    {error && <div className="notice error-notice">{error}</div>}
    <div className="student-table-wrap"><table className="student-table grades-table"><thead><tr><th>ЗАДАНИЕ</th><th>ОЦЕНКА</th><th>ОПУБЛИКОВАНО</th></tr></thead><tbody>{grades.map((grade, index) => <tr key={String(grade.id ?? index)}><td><Link className="student-course-link" href={`/student/assignments/${String(grade.assignment_id ?? "")}`}>{String(grade.assignment_title ?? "Задание")}</Link>{(grade.feedback || (Array.isArray(grade.criteria) && grade.criteria.length)) ? <details><summary>Обратная связь и критерии</summary><p>{String(grade.feedback ?? "")}</p>{Array.isArray(grade.criteria) && (grade.criteria as { criterion_id: string; points: number; comment: string }[]).map((criterion, i) => <p key={i}>{criterion.criterion_id}: {criterion.points} · {criterion.comment}</p>)}</details> : null}</td><td className="student-code">{String(grade.points ?? "—")} / {String(grade.maximum_score ?? "—")}</td><td>{grade.published_at ? new Date(String(grade.published_at)).toLocaleDateString("ru-RU") : "—"}</td></tr>)}</tbody></table></div>
    {!grades.length && !error && <div className="student-empty"><h2>Опубликованных оценок пока нет</h2><p>Преподаватель опубликует результат после проверки работы.</p></div>}
  </StudentShell>;
}
