"use client";
import { useEffect, useState } from "react";
import { downloadAuthenticatedFile } from "../lib/api";
import { loadAssignmentTemplate, type AssignmentTemplate as Template } from "../lib/assignment-template";

export function AssignmentTemplate({ offeringId, assignmentId, onRequirement }: { offeringId: string; assignmentId: string; onRequirement?: (required: boolean | null) => void }) {
  const [template, setTemplate] = useState<Template | null>(null);
  const [loading, setLoading] = useState(true), [error, setError] = useState(""), [retry, setRetry] = useState(0), [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true; setLoading(true); setTemplate(null); setError(""); onRequirement?.(null);
    loadAssignmentTemplate(offeringId, assignmentId).then(value => { if (active) { setTemplate(value); onRequirement?.(value?.required ?? false); } })
      .catch(() => { if (active) setError("Не удалось загрузить информацию о шаблоне."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [offeringId, assignmentId, retry, onRequirement]);
  async function download() {
    if (!template || busy) return;
    setBusy(true); setError("");
    try { await downloadAuthenticatedFile(`/api/materials/${template.id}/file`, template.file_name); }
    catch { setError("Не удалось скачать шаблон. Попробуйте ещё раз."); }
    finally { setBusy(false); }
  }
  if (loading) return <p role="status" className="muted">Загружаем материалы задания…</p>;
  if (!template && !error) return null;
  return <section className="assignment-template-card" aria-label="Шаблон работы">
    {template && <><div><strong>Шаблон работы</strong><span className="student-status">{template.required ? "Обязателен" : "По желанию"}</span></div>
      <p>{template.required ? "Выполните работу в этом шаблоне и отправьте заполненный файл." : "Можно использовать этот шаблон или оформить работу самостоятельно."}</p>
      <button type="button" className="button" disabled={busy} onClick={() => void download()}>{busy ? "Скачиваем…" : `Скачать ${template.file_name}`}</button></>}
    {error && <p role="alert">{error}{!template && <button type="button" className="quiet-button" onClick={() => setRetry(n => n + 1)}>Повторить</button>}</p>}
  </section>;
}
