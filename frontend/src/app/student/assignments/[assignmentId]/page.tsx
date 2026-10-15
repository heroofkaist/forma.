"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AlertTriangle, Check, FileUp, Upload } from "lucide-react";
import { SubmissionGate } from "../../../../components/submission-gate";
import { StudentShell } from "../../../../components/student-shell";
import { platformRequest } from "../../../../lib/platform";
import { academicApi, type AcademicAssignment, type Offering } from "../../../../lib/academic";

import { statusLabel, studentProcessingMessage, submissionAvailability, assignmentTypes } from "../../../../lib/presentation";

const MAX_FILE_BYTES = 30 * 1024 * 1024;

export default function StudentAssignmentPage() {
  const { assignmentId } = useParams<{ assignmentId: string }>();
  const [course, setCourse] = useState<Offering | null>(null);
  const [processing, setProcessing] = useState("");
  const [processingError, setProcessingError] = useState("");
  const [assignment, setAssignment] = useState<AcademicAssignment | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [submitted, setSubmitted] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { academicApi.assignment(assignmentId).then((value) => { setAssignment(value); void academicApi.offering(value.offering_id, "student").then(setCourse).catch(() => setCourse(null)); }).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось загрузить задание.")); }, [assignmentId]);
  const isHandwritten = assignment?.assignment_type === "problem_set";
  useEffect(() => {
    if (!file || file.type !== "application/pdf") { setPreviewUrl(""); return; }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  const programming = assignment?.assignment_type === "programming";
  const formats = programming ? "PDF, DOCX, PPTX, исходный код, ZIP" : "PDF, DOCX, PPTX";
  const accepted = programming ? ".pdf,.docx,.pptx,.py,.js,.ts,.tsx,.jsx,.java,.c,.cpp,.h,.rs,.go,.sql,.txt,.zip" : ".pdf,.docx,.pptx";
  const latest = assignment?.latest_submission;
  useEffect(()=>{const id=latest?.id;if(!id)return;let active=true;const load=()=>{void platformRequest<{jobs:{status:string;error:string}[];worker_note:string}>(`/api/document-analysis/${String(id)}/status`).then((data)=>{if(active){setProcessing(data.jobs[0]?.status??"not_scheduled");setProcessingError("");}}).catch(()=>{if(active)setProcessingError("Не удалось обновить статус. Повторим автоматически; работа остаётся сохранённой.");});};load();const timer=window.setInterval(load,10000);return()=>{active=false;window.clearInterval(timer);};},[latest?.id]);
  const due = assignment?.due_at ? new Date(assignment.due_at) : null;
  const uploadBlocked = assignment ? submissionAvailability(assignment) : "Загружаем условия задания…";

  async function submit() {
    if (!file || uploadBlocked || busy) return;
    if (file.size > MAX_FILE_BYTES) { setError("Максимальный размер файла — 30 МБ."); return; }
    setBusy(true); setError("");
    try { setSubmitted(await academicApi.submit(assignmentId, file)); setFile(null); setAssignment(await academicApi.assignment(assignmentId)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось отправить работу."); }
    finally { setBusy(false); }
  }

  return <StudentShell>
    <div className="student-breadcrumb"><Link href="/student">Мои курсы</Link><span>/</span><Link href={assignment ? `/student/courses/${assignment.offering_id}` : "/student"}>{course ? `${course.code} · ${course.course_name ?? course.name}` : "Курс"}</Link><span>/</span><span>{assignment?.title ?? "Задание"}</span></div>
    <div className="student-assignment-layout">
      <main className="student-assignment-main">
        <div className="eyebrow">{assignmentTypes[assignment?.assignment_type ?? ""] ?? "ЗАДАНИЕ"}</div><h1>{assignment?.title ?? "Задание"}</h1>
        <p className="student-assignment-course">{assignment?.description}</p>
        <div className="student-detail-table"><div><span>Открывается</span><strong>{assignment?.available_at ? new Date(assignment.available_at).toLocaleString("ru-RU") : "Сейчас"}</strong></div><div><span>Срок сдачи</span><strong>{due ? due.toLocaleString("ru-RU") : "Без срока"}</strong></div><div><span>Максимальный балл</span><strong>{assignment?.maximum_score ?? "—"}</strong></div><div><span>Форматы</span><strong>{formats}</strong></div></div>
        {isHandwritten && <div className="student-instructions"><strong>Работа от руки</strong><p>Загрузите многостраничный PDF со своим решением. Фиксированный бланк не требуется для отправки. Преподаватель проверит читаемость и содержание.</p></div>}
        {programming && <p>Код рассматривается статически. Запуск и автоматическая проверка выполнения недоступны.</p>}{assignment?.questions?.map((question, index) => <article className="student-problem" key={String(question.id ?? index)}><strong>{String(question.title ?? `Задача ${index + 1}`)}</strong><p>{String(question.statement ?? "")}</p></article>)}
      </main>
      <aside className="student-submit-panel"><h2>Ваша работа</h2>
        {latest && <div className="submission-receipt"><span className="student-status status-submitted">{statusLabel(String(latest.status ?? "submitted"))}</span><p>{String(latest.file_name ?? latest.original_filename ?? latest.filename ?? "Файл отправлен")}</p><small>Отправлено {latest.submitted_at ? new Date(String(latest.submitted_at)).toLocaleString("ru-RU") : "успешно"}</small></div>}
        {latest && processing && <p role="status">{studentProcessingMessage(processing)}</p>}
        {latest && processingError && <p role="alert">{processingError}</p>}
        {submitted && <div className="success-notice"><Check size={15} />Работа успешно отправлена. Сохраните подтверждение.</div>}
        {error && <div className="notice error-notice"><AlertTriangle size={14} />{error}</div>}
        <SubmissionGate reason={uploadBlocked}>
          <label className="student-file-picker"><input type="file" accept={accepted} onChange={(event) => { setError(""); setFile(event.target.files?.[0] ?? null); }} /><FileUp size={20} /><strong>{file?.name ?? "Выберите файл"}</strong><span>{file ? `${(file.size / 1024 / 1024).toFixed(2)} МБ` : `${formats} · до 30 МБ`}</span></label>
          {previewUrl && <object className="student-pdf-preview" data={previewUrl} type="application/pdf" aria-label="Предпросмотр PDF">Предпросмотр недоступен</object>}
          <button className="button primary full-button" disabled={!file || busy || (Boolean(latest) && !assignment?.allow_resubmission)} onClick={() => void submit()}>{busy ? "Отправляем…" : <><Upload size={14} />{latest ? "Отправить повторно" : "Подтвердить отправку"}</>}</button>
          {latest && !assignment?.allow_resubmission && <small className="muted">Повторная отправка не разрешена в настройках задания.</small>}
        </SubmissionGate>
      </aside>
    </div>
  </StudentShell>;
}
