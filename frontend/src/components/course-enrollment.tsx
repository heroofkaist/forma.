"use client";

import Link from "next/link";
import { useId, useRef, useState, type FormEvent } from "react";
import { ArrowRight, Check, KeyRound } from "lucide-react";
import { platformRequest } from "../lib/platform";
import { statusLabel, termLabel } from "../lib/presentation";

type Preview = { title: string; teacher: string; code: string; term: string; academic_year: string; approval_required: boolean; enrollment_status: string; offering_id: string };

export function CourseEnrollment({ onJoined }: { onJoined?: () => void | Promise<void> }) {
  const id = useId();
  const [code, setCode] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const inFlight = useRef(false);
  const currentStatus = status || preview?.enrollment_status;

  async function lookup(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current || code.trim().length < 3) return;
    inFlight.current = true; setBusy(true); setError(""); setStatus(""); setPreview(null);
    try { setPreview(await platformRequest<Preview>("/api/enrollment/preview", { class_code: code.trim().toUpperCase() })); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось найти курс."); }
    finally { inFlight.current = false; setBusy(false); }
  }
  async function join() {
    if (!preview || currentStatus !== "not_enrolled" || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    try {
      const result = await platformRequest<{ status: string }>("/api/enrollment/join", { class_code: code.trim().toUpperCase() });
      setStatus(result.status);
      if (result.status === "active") await onJoined?.();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось вступить в курс."); }
    finally { inFlight.current = false; setBusy(false); }
  }
  return <section className="course-enrollment" aria-labelledby={`${id}-title`}>
    <div className="course-enrollment-entry">
      <div><h2 id={`${id}-title`}>Есть код курса?</h2><p id={`${id}-hint`}>Сначала покажем курс и преподавателя.</p></div>
      <form className="course-code-form" onSubmit={event => void lookup(event)} aria-busy={busy}>
        <label className="course-code-field" htmlFor={`${id}-code`}><KeyRound size={18} aria-hidden="true"/><span className="rw-sr-only">Код курса</span><input id={`${id}-code`} placeholder="Введите код курса" required minLength={3} maxLength={32} value={code} disabled={busy} autoCapitalize="characters" autoComplete="off" spellCheck={false} aria-describedby={`${id}-hint`} onChange={event => {setCode(event.target.value); setPreview(null); setStatus(""); setError("");}}/></label>
        <button className="button primary" type="submit" disabled={busy || code.trim().length < 3}>{busy ? "Подождите…" : "Найти курс"}<ArrowRight size={17} aria-hidden="true"/></button>
      </form>
    </div>
    {error && <p role="alert" className="notice error-notice">{error}</p>}
    {preview && <div className="course-enrollment-preview" aria-live="polite">
      <div><span className="eyebrow">{preview.code} / {termLabel(preview.term)} {preview.academic_year}</span><h3>{preview.title}</h3><p>{preview.teacher || "Преподаватель курса"}</p></div>
      <div className="course-enrollment-decision">
        {currentStatus === "active" ? <><p className="course-enrollment-success" role="status"><Check size={16} aria-hidden="true"/>{status === "active" ? "Вы записаны на курс" : "Вы уже на этом курсе"}</p><Link className="button primary" href={`/student/courses/${preview.offering_id}`}>Открыть курс<ArrowRight size={17} aria-hidden="true"/></Link></>
          : currentStatus === "pending" ? <p role="status">Заявка отправлена. Ждём подтверждения преподавателя.</p>
          : ["removed", "suspended", "rejected"].includes(currentStatus ?? "") ? <p>{statusLabel(currentStatus)}. Для восстановления доступа обратитесь к преподавателю.</p>
          : currentStatus === "not_enrolled" ? <><p>{preview.approval_required ? "Преподаватель подтвердит вашу заявку." : "Проверьте сведения и подтвердите запись."}</p><button className="button primary" type="button" disabled={busy} onClick={() => void join()}>{busy ? "Отправляем…" : preview.approval_required ? "Отправить заявку" : "Записаться на курс"}<ArrowRight size={17} aria-hidden="true"/></button></>
          : <p>Статус записи уточняется. Найдите курс ещё раз.</p>}
      </div>
    </div>}
  </section>;
}
