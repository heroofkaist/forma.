import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import type { ReviewResponse } from "../../lib/review-workspace";
import { categoryLabels } from "../../lib/review-workspace";
export function SubmissionOverview({ data }: { data: ReviewResponse }) {
  const date = data.submitted_at ? new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(data.submitted_at)) : null;
  return <header className="rw-overview rw-overview-compact"><Link className="rw-back-link" href={`/teacher/assignments/${data.assignment_id}/submissions`}><ArrowLeft size={15}/> Все работы задания</Link>
    <div className="rw-overview-main"><div><div className="rw-overline">{data.title} · {categoryLabels[data.assignment_type ?? "general"] ?? "Учебная работа"}</div><h1>{data.student_name}</h1><div className="rw-submission-meta"><span>{data.file_name}</span>{date && <span>Отправлено {date}</span>}</div></div>
      <div className="rw-grade-state"><span className="rw-overline">{data.published_grade ? "ОЦЕНКА СТУДЕНТА" : "ВИДИМОСТЬ ОЦЕНКИ"}</span><strong>{data.published_grade ? `${data.published_grade.points} / ${data.published_grade.maximum_score ?? data.maximum_score}` : "Ещё не опубликована"}</strong><span>{data.published_grade ? "Студент видит этот результат" : "Сначала сохраните проверку, затем опубликуйте"}</span></div></div>
  </header>;
}
