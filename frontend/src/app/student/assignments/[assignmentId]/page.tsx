"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AlertTriangle, Check, FileUp, Upload } from "lucide-react";
import { StudentShell } from "../../../../components/student-shell";
import { academicApi, type AcademicAssignment } from "../../../../lib/academic";

const MAX_FILE_BYTES = 30 * 1024 * 1024;

export default function StudentAssignmentPage() {
  const { assignmentId } = useParams<{ assignmentId: string }>();
  const [assignment, setAssignment] = useState<AcademicAssignment | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [submitted, setSubmitted] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { academicApi.assignment(assignmentId).then(setAssignment).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось загрузить задание.")); }, [assignmentId]);
  const isHandwritten = assignment?.assignment_type === "problem_set";
  useEffect(() => {
    if (!file || file.type !== "application/pdf") { setPreviewUrl(""); return; }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  const accepted = isHandwritten ? ".pdf,application/pdf" : ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  const latest = assignment?.latest_submission;
  const due = assignment?.due_at ? new Date(assignment.due_at) : null;
  const available = assignment?.available_at ? new Date(assignment.available_at) : null;
  const notOpen = Boolean(available && available.getTime() > Date.now());
  const closed = assignment?.status === "closed" || Boolean(due && due.getTime() < Date.now() && !assignment?.allow_resubmission);

  async function submit() {
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) { setError("Максимальный размер файла — 30 МБ."); return; }
    setBusy(true); setError("");
    try { setSubmitted(await academicApi.submit(assignmentId, file)); setFile(null); setAssignment(await academicApi.assignment(assignmentId)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось отправить работу."); }
    finally { setBusy(false); }
  }

  return <StudentShell>
    <div className="student-breadcrumb"><Link href="/student">Мои курсы</Link><span>/</span><Link href={`/student/courses/${assignment?.offering_id}`}>{assignment?.title ?? "Курс"}</Link><span>/</span><span>Задание</span></div>
    <div className="student-assignment-layout">
      <main className="student-assignment-main">
        <div className="eyebrow">{assignment?.assignment_type?.replace("_", " ").toUpperCase() ?? "ЗАДАНИЕ"}</div><h1>{assignment?.title ?? "Задание"}</h1>
        <p className="student-assignment-course">{assignment?.description}</p>
        <div className="student-detail-table"><div><span>Открывается</span><strong>{assignment?.available_at ? new Date(assignment.available_at).toLocaleString("ru-RU") : "Сейчас"}</strong></div><div><span>Срок сдачи</span><strong>{due ? due.toLocaleString("ru-RU") : "Без срока"}</strong></div><div><span>Максимальный балл</span><strong>{assignment?.maximum_score ?? "—"}</strong></div><div><span>Форматы</span><strong>{isHandwritten ? "Скан PDF" : "PDF, DOCX"}</strong></div></div>
        {isHandwritten && <div className="student-instructions"><strong>Работа от руки</strong><p>Скачайте или распечатайте шаблон преподавателя, решите задачи на бланке и загрузите скан PDF. Используйте тот же масштаб и ориентацию страниц.</p>{assignment?.legacy_assignment_id && <Link href={`/assignments/${assignment.legacy_assignment_id}/template`} className="student-open-link">Открыть шаблон Forma →</Link>}</div>}
        {assignment?.questions?.map((question, index) => <article className="student-problem" key={String(question.id ?? index)}><strong>{String(question.title ?? `Задача ${index + 1}`)}</strong><p>{String(question.statement ?? "")}</p></article>)}
      </main>
      <aside className="student-submit-panel"><h2>Ваша работа</h2>
        {latest && <div className="submission-receipt"><span className="student-status status-submitted">{String(latest.status ?? "Отправлено")}</span><p>{String(latest.original_filename ?? latest.filename ?? "Файл отправлен")}</p><small>Отправлено {latest.submitted_at ? new Date(String(latest.submitted_at)).toLocaleString("ru-RU") : "успешно"}</small></div>}
        {submitted && <div className="success-notice"><Check size={15} />Работа успешно отправлена. Сохраните подтверждение.</div>}
        {error && <div className="notice error-notice"><AlertTriangle size={14} />{error}</div>}
        {notOpen ? <div className="closed-notice">Задание станет доступно {available?.toLocaleString("ru-RU")}.</div> : closed && !assignment?.allow_resubmission ? <div className="closed-notice">Срок сдачи завершён. Отправка закрыта преподавателем.</div> : <>
          <label className="student-file-picker"><input type="file" accept={accepted} onChange={(event) => { setError(""); setFile(event.target.files?.[0] ?? null); }} /><FileUp size={20} /><strong>{file?.name ?? "Выберите файл"}</strong><span>{file ? `${(file.size / 1024 / 1024).toFixed(2)} МБ` : isHandwritten ? "PDF · до 30 МБ" : "PDF или DOCX · до 30 МБ"}</span></label>
          {previewUrl && <object className="student-pdf-preview" data={previewUrl} type="application/pdf" aria-label="Предпросмотр PDF">Предпросмотр недоступен</object>}
          <button className="button primary full-button" disabled={!file || busy || (Boolean(latest) && !assignment?.allow_resubmission)} onClick={() => void submit()}>{busy ? "Отправляем…" : <><Upload size={14} />{latest ? "Отправить повторно" : "Подтвердить отправку"}</>}</button>
          {latest && !assignment?.allow_resubmission && <small className="muted">Повторная отправка не разрешена в настройках задания.</small>}
        </>}
      </aside>
    </div>
  </StudentShell>;
}
