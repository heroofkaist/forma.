import Link from "next/link";
import { ArrowLeft, FileText } from "lucide-react";
import type { ReviewResponse } from "../../lib/review-workspace";
import { categoryLabels } from "../../lib/review-workspace";
export function SubmissionOverview({ data, aiAvailable, reviewed, total }: { data: ReviewResponse; aiAvailable: boolean; reviewed: number; total: number }) {
  const date = data.submitted_at ? new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(data.submitted_at)) : null;
  return <header className="rw-overview"><Link className="rw-back-link" href={`/teacher/assignments/${data.assignment_id}/submissions`}><ArrowLeft size={14}/> К работам задания</Link>
    <div className="rw-overview-main"><div><div className="rw-overline">ПРОВЕРКА РАБОТЫ <span> / {categoryLabels[data.assignment_type ?? "general"] ?? "Учебная работа"}</span></div><h1>{data.title}</h1><div className="rw-submission-meta"><strong>{data.student_name}</strong>{date && <span>Сдано {date}</span>}<span><FileText size={13}/> {data.structure?.pages.length ?? "—"} стр.</span></div></div>
      <div className="rw-grade-state"><span className="rw-overline">ОФИЦИАЛЬНАЯ ОЦЕНКА</span><strong>{data.published_grade ? `${data.published_grade.points} / ${data.published_grade.maximum_score ?? data.maximum_score}` : "Не выставлена"}</strong><span>{data.published_grade ? "Опубликована студенту" : "Публикация только после проверки"}</span></div></div>
    <div className="rw-overview-status"><span className="rw-status">{reviewed} из {total} критериев проверено</span><span className="rw-status">{aiAvailable ? "Предложения ИИ доступны" : "Ручная проверка"}</span>{data.reviews[0] && <span className="rw-status">Ручная проверка сохранена</span>}</div>
  </header>;
}
