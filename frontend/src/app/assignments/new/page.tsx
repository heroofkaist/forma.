"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { AppShell } from "../../../components/app-shell";
import { academicApi, type Offering } from "../../../lib/academic";

export default function NewAssignmentPage() {
  const router = useRouter();
  const [offerings, setOfferings] = useState<Offering[]>([]);
  const [offeringId, setOfferingId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { academicApi.offerings().then((items) => { setOfferings(items); setOfferingId(items[0]?.id ?? ""); }).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось загрузить курсы.")).finally(() => setLoading(false)); }, []);
  async function submit(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError("");
    try {
      const created = await academicApi.createAssignment({ offering_id: offeringId, title: title.trim(), description, assignment_type: "problem_set", originality_enabled: false });
      router.push(`/teacher/assignments/${created.id}/submissions`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось создать задание."); }
    finally { setSaving(false); }
  }
  return <AppShell><section className="page-heading compact-heading"><div><h1>Создать задание</h1><p>Студенты отправляют собственный многостраничный PDF. Бланк, области ответов и эталонное решение не требуются.</p></div></section>
    {error && <div className="notice error-notice" role="alert">{error}</div>}
    {loading ? <p>Загружаем курсы…</p> : !offerings.length ? <p>Сначала <Link href="/teacher/courses/new">создайте курс</Link>.</p> : <form className="auth-form" onSubmit={submit}>
      <label>Учебный поток<select required value={offeringId} onChange={(event) => setOfferingId(event.target.value)}>{offerings.map((item) => <option key={item.id} value={item.id}>{item.course_name ?? item.name} · {item.term} {item.academic_year} · {item.section}</option>)}</select></label>
      <label>Название<input required maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} /></label>
      <label>Инструкции<textarea maxLength={5000} rows={6} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
      <p>После создания можно добавить вопросы отдельным файлом. Анализ предлагает структуру решения и не выставляет оценки.</p>
      <button className="button primary" disabled={saving || !offeringId || !title.trim()}>{saving ? "Сохраняем…" : "Создать задание"}</button>
    </form>}
  </AppShell>;
}
