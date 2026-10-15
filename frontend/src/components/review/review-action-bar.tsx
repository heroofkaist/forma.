"use client";
import { Check, Save, Send } from "lucide-react";
export function ReviewActionBar({ dirty, busy, hasSaved, total, maximum, error, onSave, onConfirm, onPublish, publishable }: { dirty: boolean; busy: boolean; hasSaved: boolean; total: number | null; maximum: number; error: string | null; onSave: () => void; onConfirm: () => void; onPublish: () => void; publishable: boolean }) {
  return <footer className="rw-action-bar" aria-label="Сохранение и публикация"><div className="rw-save-state" role="status"><span className={dirty ? "rw-unsaved-dot" : "rw-saved-dot"}/><div><strong>{busy ? "Сохранение…" : dirty ? "Есть несохранённые изменения" : hasSaved ? "Изменения сохранены" : "Проверка ещё не сохранена"}</strong><span>{error ?? (total === null ? "Балл не определён" : `Черновик: ${total} / ${maximum}`)}</span></div></div>
    <div className="rw-review-actions"><button className="rw-button" disabled={busy || !!error} onClick={onSave}><Save size={14}/> Сохранить черновик</button><button className="rw-button" disabled={busy || !!error} onClick={onConfirm}><Check size={14}/> Подтвердить критерии</button><button className="rw-button rw-primary" disabled={busy || dirty || !publishable} onClick={onPublish}><Send size={14}/> Опубликовать оценку</button></div>
  </footer>;
}
