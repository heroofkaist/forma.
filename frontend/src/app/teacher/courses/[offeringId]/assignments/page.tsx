"use client";
import { statusLabel, termLabel } from "../../../../../lib/presentation";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { CourseMaterials } from "../../../../../components/course-materials";
import { AppShell } from "../../../../../components/app-shell";
import { academicApi, type AcademicAssignment, type Offering } from "../../../../../lib/academic";

const types = [["problem_set", "Задачи"], ["essay", "Эссе"], ["lab_report", "Лабораторный отчёт"], ["presentation", "Презентация"], ["research_report", "Исследовательский отчёт"], ["programming", "Программирование"], ["general", "Документ"]] as const;
const localDate = (date: Date) => new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
const isoDate = (value: string) => value ? new Date(value).toISOString() : null;

export default function TeacherAssignmentsPage() {
  const { offeringId } = useParams<{ offeringId: string }>();
  const [offering, setOffering] = useState<Offering | null>(null);
  const [pastAssignments, setPastAssignments] = useState<AcademicAssignment[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [reuseId, setReuseId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [criteria, setCriteria] = useState([{ description: "", maximum_points: "100" }]);
  const [form, setForm] = useState({ title: "", assignment_type: "lab_report", description: "", available_at: localDate(new Date()), due_at: localDate(new Date(Date.now() + 7 * 86400000)), maximum_score: "100", allow_resubmission: false, originality_enabled: true, originality_scope: "family_then_course" });
  async function load() {
    try {
      const current = await academicApi.offering(offeringId);
      setOffering(current);
      const offerings = await academicApi.offerings();
      setPastAssignments(offerings.flatMap((item) => item.assignments ?? []).filter((assignment) => assignment.offering_id !== offeringId));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось загрузить задания потока."); }
  }
  useEffect(() => { void load(); }, [offeringId]);
  async function createAssignment(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await academicApi.createAssignment({ ...form, offering_id: offeringId, available_at: isoDate(form.available_at), due_at: isoDate(form.due_at), maximum_score: Number(form.maximum_score), questions: [{ title: form.title, statement: form.description, maximum_points: Number(form.maximum_score), criteria: criteria.filter((item) => item.description.trim()).map((item, index) => ({ id: `c${index + 1}`, description: item.description, maximum_points: Number(item.maximum_points) })) }] });
      setShowCreate(false); setCriteria([{ description: "", maximum_points: "100" }]); await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось создать задание."); }
    finally { setBusy(false); }
  }
  async function reuseAssignment() {
    if (!reuseId) return;
    setBusy(true); setError("");
    try {
      await academicApi.reuseAssignment(reuseId, { offering_id: offeringId, available_at: isoDate(form.available_at), due_at: isoDate(form.due_at), copy_rubric: true, copy_reference_solution: true, copy_template: true });
      setReuseId(""); await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось повторно использовать задание."); }
    finally { setBusy(false); }
  }
  const assignments = useMemo(() => offering?.assignments ?? [], [offering]);
  return <AppShell>
    <div className="breadcrumbs-inline"><Link href="/teacher">Учебные потоки</Link><span>/</span><span>{offering?.code} · {termLabel(offering?.term)} {offering?.academic_year}</span></div>
    <section className="academic-heading"><div><div className="eyebrow">{offering?.code} · {termLabel(offering?.term)} {offering?.academic_year}</div><h1>{offering?.course_name ?? offering?.name ?? "Задания курса"}</h1><p>Управление заданиями. Работы прошлых потоков остаются в архиве.</p></div><button className="button primary" onClick={() => setShowCreate(!showCreate)}>Новое задание</button></section>
    {error && <div className="notice error-notice">{error}</div>}
    {showCreate && <form className="academic-create-form" onSubmit={(event) => void createAssignment(event)}><div className="academic-form-grid"><label>Название<input required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label><label>Тип<select value={form.assignment_type} onChange={(event) => setForm({ ...form, assignment_type: event.target.value, originality_enabled: ["essay", "lab_report"].includes(event.target.value) })}>{types.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><label>Доступно с<input type="datetime-local" value={form.available_at} onChange={(event) => setForm({ ...form, available_at: event.target.value })} /></label><label>Срок сдачи<input type="datetime-local" value={form.due_at} onChange={(event) => setForm({ ...form, due_at: event.target.value })} /></label><label>Макс. балл<input type="number" min="0.1" step="0.5" value={form.maximum_score} onChange={(event) => setForm({ ...form, maximum_score: event.target.value })} /></label></div><label className="academic-description">Описание<textarea rows={3} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label><label className="academic-check"><input type="checkbox" checked={form.allow_resubmission} onChange={(event) => setForm({ ...form, allow_resubmission: event.target.checked })} />Разрешить повторную отправку</label><label className="academic-check"><input type="checkbox" checked={form.originality_enabled} onChange={(event) => setForm({ ...form, originality_enabled: event.target.checked })} />Проверять сходство с разрешённым архивом</label><fieldset className="rubric-editor"><legend>Критерии оценивания</legend><p>Опишите критерии и баллы. Их сумма не должна превышать максимум задания. Ручной шаблон не требуется для отправки.</p>{criteria.map((criterion, index) => <div className="academic-form-grid" key={index}><label>Критерий {index + 1}<input maxLength={1000} value={criterion.description} onChange={(event) => setCriteria(criteria.map((item, i) => i === index ? { ...item, description: event.target.value } : item))} /></label><label>Баллы<input type="number" min="0.1" max={10000} step="0.5" value={criterion.maximum_points} onChange={(event) => setCriteria(criteria.map((item, i) => i === index ? { ...item, maximum_points: event.target.value } : item))} /></label><button type="button" className="quiet-button" onClick={() => setCriteria(criteria.filter((_, i) => i !== index))}>Удалить критерий</button></div>)}<button type="button" className="button" disabled={criteria.length >= 50} onClick={() => setCriteria([...criteria, { description: "", maximum_points: "10" }])}>Добавить критерий</button><p>Сумма: {criteria.filter((item) => item.description.trim()).reduce((sum, item) => sum + Number(item.maximum_points), 0)} / {form.maximum_score}</p></fieldset><button className="button primary" disabled={busy}>{busy ? "Сохраняем…" : "Создать задание"}</button></form>}
    <div className="reuse-assignment-row"><span>Повторно использовать прошлое задание</span><select aria-label="Выберите прошлое задание" value={reuseId} onChange={(event) => setReuseId(event.target.value)}><option value="">Выберите из семейства…</option>{pastAssignments.map((assignment) => <option key={assignment.id} value={assignment.id}>{assignment.title} · {assignment.assignment_type}</option>)}</select><button className="button secondary" disabled={!reuseId || busy} onClick={() => void reuseAssignment()}>Повторно использовать</button></div>
    <div className="academic-section-header"><strong>ЗАДАНИЯ</strong><span>{assignments.length}</span></div>
    <div className="academic-assignment-table"><div className="academic-assignment-row academic-table-head"><span>НАЗВАНИЕ</span><span>ТИП</span><span>СРОК</span><span>РАБОТЫ</span><span>ОРИГИНАЛЬНОСТЬ</span><span>СТАТУС</span><span></span></div>{assignments.map((assignment) => <div className="academic-assignment-row" key={assignment.id}><strong>{assignment.title}{assignment.reused_from && <small>ПОВТОРНО ИСПОЛЬЗОВАНО</small>}</strong><span>{types.find(([key]) => key === assignment.assignment_type)?.[1] ?? assignment.assignment_type}</span><span>{assignment.due_at ? new Date(assignment.due_at).toLocaleDateString("ru-RU") : "—"}</span><span>{assignment.submission_count ?? "—"}</span><span>{assignment.originality_enabled ? <Link href="/teacher/originality">Отчёты</Link> : "—"}</span><span className="student-status">{statusLabel(assignment.status)}</span><div className="academic-row-actions"><Link href={`/teacher/assignments/${assignment.id}/submissions`}>Работы и проверка</Link>{assignment.legacy_assignment_id && <><Link href={`/assignments/${assignment.legacy_assignment_id}/template`}>Доп. шаблон</Link><Link href={`/teacher/assignments/${assignment.id}/submissions`}>Оценки</Link></>}<button onClick={() => void academicApi.publish(assignment.id).then(() => load()).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось опубликовать оценки."))}>Опубликовать оценки</button></div></div>)}</div>
    {!assignments.length && <div className="student-empty">В этом потоке ещё нет заданий.</div>}
    <CourseMaterials offeringId={offeringId} teacher />
  </AppShell>;
}
