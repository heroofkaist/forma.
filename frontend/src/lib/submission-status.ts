import {scoreLabel} from "./teacher-display";
export type SubmissionSummary = {
  review_status: "unreviewed" | "draft" | "confirmed" | "published";
  review_points: number | null; review_maximum: number; has_draft: boolean;
  processing_status: string; processing_error: string;
};
export function humanReviewLabel(item: SubmissionSummary): string {
  const score = item.review_points === null ? "" : ` · ${scoreLabel(item.review_points,item.review_maximum)} / ${scoreLabel(item.review_maximum)}`;
  if (item.review_status === "published") return `Опубликована студенту${score}`;
  if (item.review_status === "confirmed") return `Проверка подтверждена${score} · не опубликована`;
  if (item.review_status === "draft") return "Сохранён черновик · не подтверждён";
  return "Не проверено преподавателем";
}
export function aiProcessingLabel(status: string): string {
  if (["complete", "completed", "cached"].includes(status)) return "ИИ: анализ завершён";
  if (["awaiting_source", "queued", "extracting", "interpreting", "processing"].includes(status)) return "ИИ: анализ выполняется";
  if (status === "needs_review") return "ИИ: материалы анализа требуют проверки";
  if (status === "awaiting_budget") return "ИИ: анализ приостановлен";
  if (["failed", "cancelled"].includes(status)) return "ИИ: анализ не выполнен";
  if (status === "not_scheduled") return "ИИ: анализ не запланирован";
  return "ИИ: статус анализа уточняется";
}
