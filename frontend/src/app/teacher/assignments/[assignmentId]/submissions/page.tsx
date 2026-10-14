"use client";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AssignmentBriefs } from "../../../../../components/assignment-briefs";
import { AppShell } from "../../../../../components/app-shell";
import { platformRequest } from "../../../../../lib/platform";
type Submissions = { title: string; offering_id: string; items: { id: string; student_name: string; file_name: string; status: string; submitted_at: string }[] };
export default function SubmissionsPage() {
  const { assignmentId } = useParams<{ assignmentId: string }>(); const [data, setData] = useState<Submissions | null>(null); const [error, setError] = useState("");
  useEffect(() => { platformRequest<Submissions>(`/api/assignment-submissions/${assignmentId}`).then(setData).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось загрузить работы.")); }, [assignmentId]);
  return <AppShell><section className="academic-heading"><div><div className="eyebrow">ЗАДАНИЕ · РАБОТЫ</div><h1>{data?.title ?? "Работы студентов"}</h1>{data && <Link href={`/teacher/courses/${data.offering_id}/assignments`}>К заданиям курса →</Link>}</div></section>{error && <div className="notice error-notice" role="alert">{error}</div>}
    {data && <AssignmentBriefs assignmentId={assignmentId}/>}
    {!data && !error ? <p>Загружаем работы…</p> : data && <div className="student-table-wrap"><table className="student-table"><thead><tr><th>СТУДЕНТ</th><th>ФАЙЛ</th><th>ОТПРАВЛЕНО</th><th>СТАТУС</th><th></th></tr></thead><tbody>{data.items.map((item) => <tr key={item.id}><td>{item.student_name}</td><td>{item.file_name}</td><td>{new Date(item.submitted_at).toLocaleString("ru-RU")}</td><td>{item.status === "completed" ? "Оценка опубликована" : "Ожидает проверки"}</td><td><Link href={`/teacher/submissions/${item.id}/review`}>Проверить →</Link></td></tr>)}</tbody></table>{!data.items.length && <div className="student-empty">Работы пока не отправлены.</div>}</div>}
  </AppShell>;
}
