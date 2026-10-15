import { criterionTitle, type PublishedGrade } from "../lib/published-result";

export function PublishedResult({ grade, id = `result-${grade.id}` }: { grade: PublishedGrade; id?: string }) {
  return <section className="student-problem" id={id} aria-label="Опубликованный результат">
    <h2>Результат опубликован</h2>
    <p><strong>{grade.points} / {grade.maximum_score}</strong></p>
    {grade.published_at && <p>Опубликовано {new Date(grade.published_at).toLocaleString("ru-RU")}</p>}
    {grade.feedback && <p style={{ whiteSpace: "pre-wrap" }}>{grade.feedback}</p>}
    {grade.criteria?.length > 0 && <dl>{grade.criteria.map((criterion, index) => <div key={JSON.stringify([criterion.question_id, criterion.criterion_id])}>
      <dt><strong>{criterionTitle(criterion, index)}</strong> · {criterion.points}{criterion.maximum_points != null ? ` / ${criterion.maximum_points}` : ""}</dt>
      {criterion.comment && <dd style={{ whiteSpace: "pre-wrap" }}>{criterion.comment}</dd>}
    </div>)}</dl>}
  </section>;
}
