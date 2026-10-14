"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpRight, Plus, Search, Trash2 } from "lucide-react";
import { AppShell, StatusLabel } from "../components/app-shell";
import { api } from "../lib/api";
import type { Assignment } from "../lib/types";

export default function AssignmentsPage() {
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [sortAsc, setSortAsc] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState("");
  const [deleteBusy, setDeleteBusy] = useState(false);

  useEffect(() => {
    api.assignments().then(setAssignments).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось загрузить задания.")).finally(() => setLoading(false));
  }, []);

  const filtered = assignments.filter((item) => item.title.toLowerCase().includes(query.toLowerCase())).sort((a, b) => {
    const diff = Date.parse(a.created_at ?? "") - Date.parse(b.created_at ?? "");
    return sortAsc ? diff : -diff;
  });

  async function removeAssignment(assignmentId: string) {
    setDeleteBusy(true);
    setError("");
    try {
      await api.deleteAssignment(assignmentId);
      setAssignments((items) => items.filter((item) => item.id !== assignmentId));
      setConfirmDelete("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось удалить задание.");
    } finally {
      setDeleteBusy(false);
    }
  }

  return <AppShell>
    <section className="page-heading">
      <div><div className="eyebrow">ПРЕПОДАВАНИЕ · РАБОЧЕЕ ПРОСТРАНСТВО</div><h1>Задания</h1><p className="heading-subtitle">Создавайте проверочные работы и оценивайте решения с помощью понятных критериев.</p></div>
      <Link className="button primary" href="/assignments/new"><Plus size={16} />Новое задание</Link>
    </section>
    {error && <div className="notice error-notice">{error}</div>}
    <div className="table-toolbar">
      <label className="search-field"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Найти задание" /></label>
      <button className="quiet-button" onClick={() => setSortAsc(!sortAsc)}>{sortAsc ? <ArrowUp size={14} /> : <ArrowDown size={14} />}По дате</button>
    </div>
    {loading ? <div className="table-loading"><span className="spinner" />Загружаем задания…</div> : filtered.length > 0 ? <div className="assignment-table">
      <div className="assignment-row table-head"><span>НАЗВАНИЕ</span><span>ПРЕДМЕТ</span><span>ВОПРОСЫ</span><span>РАБОТЫ</span><span>ПРОВЕРКА</span><span>СТАТУС</span></div>
      {filtered.map((assignment) => <div className="assignment-row" key={assignment.id}>
        <span className="assignment-title"><Link href={`/assignments/${assignment.id}/review`}><strong>{assignment.title}</strong></Link>{assignment.demo_mode && <span className="demo-tag">ДЕМО</span>}<small>{assignment.created_at ? new Date(assignment.created_at).toLocaleDateString("ru-RU") : "Локальное задание"}</small></span>
        <span>{assignment.subject === "Physics" ? "Физика" : assignment.subject === "Mathematics" ? "Математика" : assignment.subject}</span>
        <span>{assignment.questions?.length ?? 0}</span>
        <span>{assignment.submission_count ?? 0}</span>
        <span className="review-cell">{assignment.reviewed_count ?? 0}<span className="muted"> / {assignment.submission_count ?? 0}</span></span>
        <span className="assignment-end"><StatusLabel status={assignment.status} />{confirmDelete === assignment.id ? <span className="inline-confirm"><button disabled={deleteBusy} onClick={() => void removeAssignment(assignment.id)}>Да</button><button onClick={() => setConfirmDelete("")}>Нет</button></span> : <><button className="delete-assignment" title="Удалить задание и связанные файлы" aria-label={`Удалить ${assignment.title}`} onClick={() => setConfirmDelete(assignment.id)}><Trash2 size={13} /></button><Link className="row-open" href={`/assignments/${assignment.id}/review`} title="Открыть задание"><ArrowUpRight size={15} /></Link></>}</span>
      </div>)}
    </div> : <div className="empty-state"><div className="empty-icon"><ArrowUpRight size={18} /></div><h2>{query ? "Ничего не найдено" : "Создайте первое задание"}</h2><p>{query ? "Попробуйте изменить поисковый запрос." : "Добавьте вопросы и критерии оценивания, затем загрузите работы класса."}</p>{!query && <Link className="button primary" href="/assignments/new"><Plus size={16} />Создать задание</Link>}</div>}
    <div className="privacy-note">Доступ к работам определяется правами преподавателя. Оценки становятся доступны студенту после публикации.</div>
  </AppShell>;
}
