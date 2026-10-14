"use client";
import { FormEvent, useState } from "react";
import Link from "next/link";
import { StudentShell } from "../../../components/student-shell";
import { platformRequest } from "../../../lib/platform";
type Preview = { title: string; teacher: string; term: string; academic_year: string; approval_required: boolean; enrollment_status: string; offering_id: string };
export default function JoinPage() {
  const [code, setCode] = useState(""); const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const [status, setStatus] = useState("");
  async function lookup(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setStatus(""); setPreview(null);
    try { setPreview(await platformRequest<Preview>("/api/enrollment/preview", { class_code: code })); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось найти курс."); } finally { setBusy(false); }
  }
  async function join() {
    setBusy(true); setError("");
    try { const result = await platformRequest<{ status: string }>("/api/enrollment/join", { class_code: code }); setStatus(result.status); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось вступить в курс."); } finally { setBusy(false); }
  }
  return <StudentShell><div className="student-page-title"><div><div className="eyebrow">ЗАПИСЬ НА КУРС</div><h1>Вступить в курс</h1><p>Введите код, полученный от преподавателя, и проверьте сведения курса.</p></div></div>
    <form className="auth-form platform-form" onSubmit={(event) => void lookup(event)}><label>Код курса<input required maxLength={32} value={code} autoCapitalize="characters" onChange={(event) => { setCode(event.target.value); setPreview(null); setStatus(""); }} /></label><button className="button primary" disabled={busy}>{busy ? "Проверяем…" : "Найти курс"}</button></form>
    {error && <div role="alert" className="notice error-notice">{error}</div>}
    {preview && <section className="platform-panel"><h2>{preview.title}</h2><p>{preview.teacher} · {preview.term} {preview.academic_year}</p><p>Статус записи: {status || preview.enrollment_status}</p>
      {status === "active" || preview.enrollment_status === "active" ? <Link className="button primary" href={`/student/courses/${preview.offering_id}`}>Открыть курс</Link>
        : status === "pending" || preview.enrollment_status === "pending" ? <p role="status">Заявка ожидает решения преподавателя.</p>
        : ["removed", "suspended", "rejected"].includes(status || preview.enrollment_status) ? <p>Для восстановления доступа обратитесь к преподавателю.</p>
        : <button className="button primary" disabled={busy} onClick={() => void join()}>{preview.approval_required ? "Отправить заявку" : "Подтвердить запись"}</button>}
    </section>}
  </StudentShell>;
}
