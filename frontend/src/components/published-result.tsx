import {scoreLabel,dateLabel} from "../lib/teacher-display";
import { criterionTitle, type PublishedGrade } from "../lib/published-result";

export function PublishedResult({ grade, id = `result-${grade.id}` }: { grade: PublishedGrade; id?: string }) {
  const next=grade.criteria?.find(c=>c.maximum_points!=null&&c.points<c.maximum_points&&c.comment.trim());
  return <section className="student-problem" id={id} aria-label="Опубликованный результат">
    <h2>Результат опубликован</h2>
    <p><strong>{scoreLabel(grade.points,grade.maximum_score)} / {scoreLabel(grade.maximum_score)}</strong></p>
    {grade.published_at && <p>Опубликовано {dateLabel(grade.published_at)}</p>}
    {grade.feedback && <p style={{ whiteSpace: "pre-wrap" }}>{grade.feedback}</p>}
    {next&&<aside className="student-next-step"><strong>На чём сосредоточиться дальше</strong><p>{next.comment}</p><small>Из замечания преподавателя к критерию «{criterionTitle(next,grade.criteria.indexOf(next))}».</small></aside>}
    {grade.criteria?.length > 0 && <dl>{grade.criteria.map((criterion, index) => <div key={JSON.stringify([criterion.question_id, criterion.criterion_id])}>
      <dt><strong>{criterionTitle(criterion, index)}</strong> · {scoreLabel(criterion.points,criterion.maximum_points??10000)}{criterion.maximum_points != null ? ` / ${scoreLabel(criterion.maximum_points)}` : ""}</dt>
      {criterion.comment && <dd style={{ whiteSpace: "pre-wrap" }}>{criterion.comment}</dd>}
    </div>)}</dl>}
  </section>;
}
