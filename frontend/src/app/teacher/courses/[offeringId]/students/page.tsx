"use client";
import { statusLabel } from "../../../../../lib/presentation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AppShell } from "../../../../../components/app-shell";
import { downloadAuthenticatedFile } from "../../../../../lib/api";
import { platformRequest } from "../../../../../lib/platform";
type Roster = { class_code: string; enabled: boolean; approval_required: boolean; capacity: number | null; opens_at: string | null; closes_at: string | null; items: { id: string; student_name: string; status: string }[] };
function localDate(value: string | null) { if (!value) return ""; const date = new Date(value); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16); }
export default function Students() {
  const { offeringId } = useParams<{ offeringId: string }>(); const path = `/api/courses/${offeringId}`;
  const [data, setData] = useState<Roster | null>(null); const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const [notice, setNotice] = useState("");
  const load = useCallback(async () => { try { setData(await platformRequest<Roster>(`${path}/enrollment`)); } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось загрузить список."); } }, [path]);
  useEffect(() => { void load(); }, [load]);
  async function action(run: () => Promise<unknown>) { setBusy(true); setError(""); setNotice(""); try { await run(); await load(); setNotice("Изменения сохранены."); } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось сохранить."); } finally { setBusy(false); } }
  async function save(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const fields = Object.fromEntries(new FormData(event.currentTarget)); await action(() => platformRequest(`${path}/enrollment`, { enabled: fields.enabled === "on", approval_required: fields.approval_required === "on", capacity: fields.capacity ? Number(fields.capacity) : null, opens_at: fields.opens_at ? new Date(String(fields.opens_at)).toISOString() : null, closes_at: fields.closes_at ? new Date(String(fields.closes_at)).toISOString() : null }, "PUT")); }
  return <AppShell><section className="academic-heading"><div><div className="eyebrow">КУРС · УЧАСТНИКИ</div><h1>Студенты и запись</h1><Link href={`/teacher/courses/${offeringId}/assignments`}>К заданиям курса →</Link></div></section>
    {error && <div role="alert" className="notice error-notice">{error}</div>}{notice && <div role="status" className="notice">{notice}</div>}
    {!data ? <p>Загружаем список…</p> : <>
      <section className="platform-panel"><h2>Код записи</h2><p><strong>{data.class_code}</strong> · {data.enabled ? "Включён" : "Отключён"}</p><button className="button" onClick={() => void navigator.clipboard.writeText(data.class_code).then(() => setNotice("Код скопирован.")).catch(() => setError("Скопируйте код вручную."))}>Копировать</button><button className="button" disabled={busy} onClick={() => void action(() => platformRequest(`${path}/rotate-code`, {}))}>Заменить код</button><p>Замена или отключение кода сохраняет существующие записи студентов.</p></section>
      <form key={`${data.enabled}-${data.approval_required}-${data.capacity}-${data.opens_at}-${data.closes_at}`} className="academic-form-grid" onSubmit={(event) => void save(event)}><label><input name="enabled" type="checkbox" defaultChecked={data.enabled} />Принимать новые записи</label><label><input name="approval_required" type="checkbox" defaultChecked={data.approval_required} />Ручное одобрение</label><label>Количество мест<input name="capacity" type="number" min={1} max={100000} defaultValue={data.capacity ?? ""} /></label><label>Открытие<input name="opens_at" type="datetime-local" defaultValue={localDate(data.opens_at)} /></label><label>Закрытие<input name="closes_at" type="datetime-local" defaultValue={localDate(data.closes_at)} /></label><button className="button primary" disabled={busy}>Сохранить политику</button></form>
      <div className="student-toolbar"><span>{data.items.filter((item) => item.status === "active").length} студентов · {data.items.filter((item) => item.status === "pending").length} заявок</span><button className="button" onClick={() => void downloadAuthenticatedFile(`${path}/roster.csv`, "roster.csv").catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось скачать список."))}>Скачать список</button></div>
      <div className="student-table-wrap"><table className="student-table"><thead><tr><th>СТУДЕНТ</th><th>СТАТУС</th><th>ДЕЙСТВИЯ</th></tr></thead><tbody>{data.items.map((item) => <tr key={item.id}><td>{item.student_name}</td><td>{statusLabel(item.status)}</td><td>{[...(item.status !== "active" ? ["active"] : []), ...(item.status === "pending" ? ["rejected"] : []), ...(item.status === "active" ? ["suspended", "removed"] : [])].map((status) => <button className="quiet-button" key={status} disabled={busy} onClick={() => void action(() => platformRequest(`${path}/enrollment/${item.id}`, { status }, "PATCH"))}>{{active:"Принять",rejected:"Отклонить",suspended:"Приостановить",removed:"Удалить"}[status]}</button>)}</td></tr>)}</tbody></table>{!data.items.length && <p>Студентов пока нет. Передайте им код записи.</p>}</div>
    </>}
  </AppShell>;
}
