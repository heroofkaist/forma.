"use client";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { API_URL, authenticatedFetch, downloadAuthenticatedFile } from "../lib/api";
import { platformRequest } from "../lib/platform";
type Material = { id: string; title: string; visibility: string; file_name: string; status: string; created_at: string; warnings: string[]; tags: string };
export function CourseMaterials({ offeringId, teacher = false }: { offeringId: string; teacher?: boolean }) {
  const [items, setItems] = useState<Material[]>([]); const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(true);
  const load = useCallback(async () => { try { const data = await platformRequest<{ items: Material[] }>(`/api/course-materials/${offeringId}`); setItems(data.items); } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось загрузить материалы."); } finally { setLoading(false); } }, [offeringId]);
  useEffect(() => { void load(); }, [load]);
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form); const file = data.get("file");
    if (!(file instanceof File) || file.size > 30 * 1024 * 1024) { setError("Выберите файл до 30 МБ."); return; }
    setBusy(true); setError("");
    try { const response = await authenticatedFetch(`${API_URL}/api/course-materials/${offeringId}`, { method: "POST", body: data }); const body = await response.json(); if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Не удалось загрузить материал."); form.reset(); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось загрузить материал."); } finally { setBusy(false); }
  }
  return <section id="materials" className="platform-panel"><h2>{teacher ? "Материалы курса и эталоны" : "Материалы курса"}</h2>
    {teacher && <form className="academic-form-grid" onSubmit={(event) => void upload(event)}><label>Название<input name="title" required maxLength={200} /></label><label>Доступ<select name="visibility"><option value="teacher_only">Только преподаватель</option><option value="student_visible">Студенты курса</option></select></label><label>Темы<input name="tags" maxLength={500} /></label><label>PDF, DOCX, PPTX · до 30 МБ<input name="file" type="file" accept=".pdf,.docx,.pptx" required /></label><button className="button primary" disabled={busy}>{busy ? "Обрабатываем…" : "Добавить материал"}</button></form>}
    {error && <div role="alert" className="notice error-notice">{error}</div>}
    {loading ? <p>Загружаем материалы…</p> : items.length ? <div className="student-table-wrap"><table className="student-table"><thead><tr><th>МАТЕРИАЛ</th>{teacher && <th>ДОСТУП</th>}<th>СТАТУС</th><th></th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><strong>{item.title}</strong><small>{item.tags}</small>{item.warnings.length > 0 && <details><summary>Ограничения извлечения</summary>{item.warnings.map((warning, index) => <p key={index}>{warning}</p>)}</details>}</td>{teacher && <td>{item.visibility === "teacher_only" ? "Преподаватель" : "Студенты"}</td>}<td>{item.status}</td><td><button className="quiet-button" onClick={() => void downloadAuthenticatedFile(`/api/materials/${item.id}/file`, item.file_name).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось скачать файл."))}>Скачать</button></td></tr>)}</tbody></table></div> : <p>Материалы пока не добавлены.</p>}
  </section>;
}
