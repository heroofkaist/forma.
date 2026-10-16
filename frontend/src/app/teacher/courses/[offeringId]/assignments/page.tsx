"use client";
import { statusLabel, termLabel } from "../../../../../lib/presentation";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { AssignmentCreateForm } from "../../../../../components/assignment-create-form";
import { CourseArchive } from "../../../../../components/course-archive";
import { CourseMaterials } from "../../../../../components/course-materials";
import { AppShell } from "../../../../../components/app-shell";
import { academicApi, type AcademicAssignment, type Offering } from "../../../../../lib/academic";

import { copyAssignmentTemplate } from "../../../../../lib/assignment-template";
const types = [["problem_set", "Задачи"], ["essay", "Эссе"], ["lab_report", "Лабораторный отчёт"], ["presentation", "Презентация"], ["research_report", "Исследовательский отчёт"], ["programming", "Программирование"], ["general", "Документ"]] as const;
const localDate = (date: Date) => new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
const isoDate = (value: string) => value ? new Date(value).toISOString() : null;

export default function TeacherAssignmentsPage() {
  const { offeringId } = useParams<{ offeringId: string }>();
  const [offering, setOffering] = useState<Offering | null>(null);
  const [pastAssignments, setPastAssignments] = useState<AcademicAssignment[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const pendingReuse = useRef<{ id: string; sourceId: string; sourceOfferingId: string } | null>(null);
  const reuseSending = useRef(false);
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
    if (!reuseId || reuseSending.current) return;
    reuseSending.current=true;
    setBusy(true); setError("");
    try {
      if (!pendingReuse.current) {
      const source = pastAssignments.find(item => item.id === reuseId);
      if (!source) throw new Error("Выберите задание ещё раз.");
      const created = await academicApi.reuseAssignment(reuseId, { offering_id: offeringId, available_at: isoDate(form.available_at), due_at: isoDate(form.due_at), copy_rubric: true, copy_reference_solution: true, copy_template: true });
      pendingReuse.current = { id: created.id, sourceId: source.id, sourceOfferingId: source.offering_id };
      }
      const pending = pendingReuse.current;
      await copyAssignmentTemplate(pending.sourceOfferingId, pending.sourceId, offeringId, pending.id);
      pendingReuse.current=null; setReuseId(""); await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось повторно использовать задание."); }
    finally { reuseSending.current=false; setBusy(false); }
  }
  const assignments = useMemo(() => offering?.assignments ?? [], [offering]);
  return <AppShell>
    <div className="breadcrumbs-inline"><Link href="/teacher">Мои курсы</Link><span>/</span><span>{offering?.code} · {termLabel(offering?.term)} {offering?.academic_year}</span></div>
    <section className="academic-heading"><div><div className="eyebrow">{offering?.code} · {termLabel(offering?.term)} {offering?.academic_year}</div><h1>{offering?.course_name ?? offering?.name ?? "Задания курса"}</h1><p>Создавайте задания, собирайте работы и проверяйте результаты группы.</p></div><button className="button primary" aria-expanded={showCreate} aria-controls="assignment-create-region" onClick={() => setShowCreate(!showCreate)}>{showCreate ? "Закрыть форму" : "Новое задание"}</button></section>
    {error && <div className="notice error-notice" role="alert">{error}<button className="button" onClick={() => void load()}>Повторить</button></div>}
    {showCreate && <section id="assignment-create-region" aria-label="Создание задания"><AssignmentCreateForm offeringId={offeringId} onCreated={async () => {setShowCreate(false); await load();}}/></section>}
    {pastAssignments.length > 0 && <details className="assignment-instructions course-reuse"><summary>Использовать задание из другого потока</summary><div className="reuse-assignment-row"><label htmlFor="reuse-assignment">Прошлое задание</label><select id="reuse-assignment" disabled={busy || Boolean(pendingReuse.current)} value={reuseId} onChange={event => setReuseId(event.target.value)}><option value="">Выберите задание</option>{pastAssignments.map(assignment => <option key={assignment.id} value={assignment.id}>{assignment.title} · {types.find(([key]) => key === assignment.assignment_type)?.[1] ?? "Работа"}</option>)}</select><button className="button" disabled={!reuseId || busy} onClick={() => void reuseAssignment()}>{busy ? "Копируем…" : "Скопировать в этот поток"}</button></div></details>}
    <div className="assignment-section-heading"><div><h2>Задания курса</h2><p>Откройте задание, чтобы увидеть студентов, оценки и совпадения с архивом.</p></div><span>{assignments.length}</span></div>
    {!offering && !error ? <p className="student-loading" role="status">Загружаем задания…</p> : assignments.length > 0 ? <div className="student-table-wrap"><table className="student-table course-assignment-list"><thead><tr><th scope="col">ЗАДАНИЕ</th><th scope="col">СРОК СДАЧИ</th><th scope="col">РАБОТЫ</th><th scope="col">СТАТУС</th><th scope="col"><span className="rw-sr-only">Действия</span></th></tr></thead><tbody>{assignments.map(assignment => <tr key={assignment.id}><td data-label="Задание"><Link className="course-assignment-title" href={`/teacher/assignments/${assignment.id}/submissions`}>{assignment.title}</Link><small>{types.find(([key]) => key === assignment.assignment_type)?.[1] ?? "Учебная работа"}{assignment.reused_from ? " · Из прошлого потока" : ""}</small></td><td data-label="Срок сдачи">{assignment.due_at && Number.isFinite(Date.parse(assignment.due_at)) ? new Date(assignment.due_at).toLocaleDateString("ru-RU") : "Без срока"}</td><td data-label="Работы">{assignment.submission_count ?? "—"}</td><td data-label="Статус"><span className="student-status">{statusLabel(assignment.status)}</span></td><td data-label="Действия"><Link className="button" href={`/teacher/assignments/${assignment.id}/submissions`}>Открыть работы →</Link><details className="course-publish"><summary>Публикация оценок</summary><p>Публикуются готовые оценки этого задания.</p><button className="quiet-button" onClick={() => void academicApi.publish(assignment.id).then(() => load()).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось опубликовать оценки."))}>Опубликовать оценки</button></details></td></tr>)}</tbody></table></div> : offering && <div className="student-empty"><h2>Первое задание для этого потока</h2><p>Добавьте условия, срок сдачи и критерии. Файл задания и шаблон можно приложить по желанию.</p><button className="button primary" onClick={() => setShowCreate(true)}>Создать задание</button></div>}
    <CourseArchive offeringId={offeringId}/><CourseMaterials offeringId={offeringId} teacher />
  </AppShell>;
}
