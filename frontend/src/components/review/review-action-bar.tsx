"use client";
import { Check, Save, Send } from "lucide-react";
import { savedReviewLabels, type SavedReviewState } from "../../lib/review-workspace";
export function ReviewActionBar({ dirty, busy, hasSaved, total, maximum, error, onSave, onConfirm, onPublish, publishable, savedState }: { savedState: SavedReviewState; dirty: boolean; busy: boolean; hasSaved: boolean; total: number | null; maximum: number; error: string | null; onSave: () => void; onConfirm: () => void; onPublish: () => void; publishable: boolean }) {
  const published = savedState === "published" && !dirty;
  const nextIsPublish = publishable && !dirty;
  const hint = error ?? (dirty ? "Изменения пока видны только вам." : nextIsPublish ? "Проверка сохранена. Опубликуйте результат для студента." : published ? "Студент видит опубликованную оценку и комментарии." : total === null ? "Укажите балл по каждому критерию. Неполную проверку можно сохранить в черновик." : "Сохраните проверку. Публикация будет следующим шагом.");
  return <footer className="rw-action-bar rw-action-bar-guided" aria-label="Сохранение и публикация">
    <div className="rw-grade-total"><span>Итого</span><strong>{total ?? "—"}<small> / {maximum}</small></strong></div>
    <div className="rw-save-state" role="status"><div><strong>{busy ? "Сохраняем…" : dirty ? "Есть изменения" : published ? `Опубликовано: ${total ?? "—"} / ${maximum}` : hasSaved ? `${savedReviewLabels[savedState]}: ${total ?? "—"} / ${maximum}` : "Начните с оценки по критериям"}</strong><span>{hint}</span></div></div>
    <div className="rw-review-actions"><button className="rw-button rw-draft-button" disabled={busy || !!error} onClick={onSave}><Save size={15}/> В черновик</button>
      <button className="rw-button rw-primary" disabled={busy || !!error || published || (!nextIsPublish && total === null)} onClick={nextIsPublish ? onPublish : onConfirm}>{nextIsPublish ? <Send size={15}/> : <Check size={15}/>} {published ? "Оценка опубликована" : nextIsPublish ? "Опубликовать оценку" : "Сохранить проверку"}</button></div>
  </footer>;
}
