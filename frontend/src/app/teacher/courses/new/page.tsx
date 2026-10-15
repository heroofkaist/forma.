"use client";
import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "../../../../components/app-shell";
import { platformRequest } from "../../../../lib/platform";
import { useAuth } from "../../../../components/auth-provider";
export default function NewCourse() {
  const [institutions, setInstitutions] = useState<{id: string; name: string}[]>([]);
  useEffect(() => { platformRequest<{items: {id: string; name: string}[]}>("/api/institutions").then((data) => setInstitutions(data.items)).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось загрузить учреждения.")); }, []);
  const { user } = useAuth(); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ offering_id: string; class_code: string } | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const values = Object.fromEntries(new FormData(event.currentTarget));
    try { setResult(await platformRequest("/api/courses", { ...values, approval_required: values.approval_required === "on", capacity: values.capacity ? Number(values.capacity) : null, opens_at: values.opens_at ? new Date(String(values.opens_at)).toISOString() : null, closes_at: values.closes_at ? new Date(String(values.closes_at)).toISOString() : null })); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось создать курс."); } finally { setBusy(false); }
  }
  return <AppShell><section className="academic-heading"><div><div className="eyebrow">КУРСЫ</div><h1>Создать курс</h1><p>Курс и его учебный поток доступны только вам и принятым студентам.</p></div></section>
    {!["teacher", "school_admin", "platform_admin"].includes(user?.role ?? "") ? <div className="notice">Для создания курса требуется одобренная роль преподавателя и активное членство в учреждении. Публичная регистрация таких прав не выдаёт.</div> : result ? <section className="platform-panel"><h2>Курс создан</h2><p>Код для студентов: <strong>{result.class_code}</strong></p><button className="button" onClick={() => void navigator.clipboard.writeText(result.class_code).catch(() => setError("Скопируйте код вручную."))}>Копировать код</button><Link className="button primary" href={`/teacher/courses/${result.offering_id}/assignments`}>Открыть курс</Link><Link className="button" href={`/teacher/courses/${result.offering_id}/students`}>Управление записью</Link></section> : <form className="academic-form-grid" onSubmit={(event) => void submit(event)}>
      <label>Учреждение<select name="institution_id" required><option value="">Выберите учреждение</option>{institutions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Название<input name="title" required maxLength={200} placeholder="Общая физика I" /></label><label>Код курса<input name="code" required maxLength={24} placeholder="PHYS101" /></label><label>Дисциплина<input name="subject" required maxLength={200} /></label><label>Описание<textarea name="description" maxLength={5000} /></label><label>Семестр<input name="term" required defaultValue="Осень" maxLength={32} /></label><label>Учебный год<input name="academic_year" required defaultValue="2026" maxLength={12} /></label><label>Количество мест<input type="number" name="capacity" min={1} max={100000} /></label><label>Открытие записи<input type="datetime-local" name="opens_at" /></label><label>Закрытие записи<input type="datetime-local" name="closes_at" /></label><label><input name="approval_required" type="checkbox" />Принимать заявки вручную</label><button className="button primary" disabled={busy}>{busy ? "Создаём…" : "Создать курс"}</button>
    </form>}{error && <div className="notice error-notice" role="alert">{error}</div>}
  </AppShell>;
}
