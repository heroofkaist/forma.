"use client";
import { statusLabel, termLabel } from "../../../../../lib/presentation";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { AssignmentCreateForm } from "../../../../../components/assignment-create-form";
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
  const [form] = useState({available_at: localDate(new Date()), due_at: localDate(new Date(Date.now() + 7 * 86400000))});
  async function load() {
    try {
      const current = await academicApi.offering(offeringId);
      setOffering(current);
      const offerings = await academicApi.offerings();
      setPastAssignments(offerings.flatMap((item) => item.assignments ?? []).filter((assignment) => assignment.offering_id !== offeringId));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось загрузить задания потока."); }
  }
  useEffect(() => { void load(); }, [offeringId]);
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
    {showCreate && <AssignmentCreateForm offeringId={offeringId} onCreated={async () => {setShowCreate(false); await load();}}/>}
    <div className="reuse-assignment-row"><span>Повторно использовать прошлое задание</span><select aria-label="Выберите прошлое задание" value={reuseId} onChange={(event) => setReuseId(event.target.value)}><option value="">Выберите из семейства…</option>{pastAssignments.map((assignment) => <option key={assignment.id} value={assignment.id}>{assignment.title} · {assignment.assignment_type}</option>)}</select><button className="button secondary" disabled={!reuseId || busy} onClick={() => void reuseAssignment()}>Повторно использовать</button></div>
    <div className="academic-section-header"><strong>ЗАДАНИЯ</strong><span>{assignments.length}</span></div>
    <div className="academic-assignment-table"><div className="academic-assignment-row academic-table-head"><span>НАЗВАНИЕ</span><span>ТИП</span><span>СРОК</span><span>РАБОТЫ</span><span>ОРИГИНАЛЬНОСТЬ</span><span>СТАТУС</span><span></span></div>{assignments.map((assignment) => <div className="academic-assignment-row" key={assignment.id}><strong>{assignment.title}{assignment.reused_from && <small>ПОВТОРНО ИСПОЛЬЗОВАНО</small>}</strong><span>{types.find(([key]) => key === assignment.assignment_type)?.[1] ?? assignment.assignment_type}</span><span>{assignment.due_at ? new Date(assignment.due_at).toLocaleDateString("ru-RU") : "—"}</span><span>{assignment.submission_count ?? "—"}</span><span>{assignment.originality_enabled ? <Link href="/teacher/originality">Отчёты</Link> : "—"}</span><span className="student-status">{statusLabel(assignment.status)}</span><div className="academic-row-actions"><Link href={`/teacher/assignments/${assignment.id}/submissions`}>Работы и проверка</Link>{assignment.legacy_assignment_id && <><Link href={`/assignments/${assignment.legacy_assignment_id}/template`}>Доп. шаблон</Link><Link href={`/teacher/assignments/${assignment.id}/submissions`}>Оценки</Link></>}<button onClick={() => void academicApi.publish(assignment.id).then(() => load()).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось опубликовать оценки."))}>Опубликовать оценки</button></div></div>)}</div>
    {!assignments.length && <div className="student-empty">В этом потоке ещё нет заданий.</div>}
    <CourseMaterials offeringId={offeringId} teacher />
  </AppShell>;
}
