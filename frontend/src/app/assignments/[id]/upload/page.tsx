"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, Check, FileUp, LoaderCircle, Upload } from "lucide-react";
import { AppShell } from "../../../../components/app-shell";
import { ProtectedImage } from "../../../../components/protected-resource";
import { api } from "../../../../lib/api";
import type { Assignment, Answer } from "../../../../lib/types";

export default function UploadPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [assignment, setAssignment] = useState<Assignment | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [uploaded, setUploaded] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.assignment(id).then(setAssignment).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось загрузить задание."));
  }, [id]);

  async function upload() {
    if (!file) return;
    setWorking(true);
    setError("");
    try {
      const result = await api.upload(id, file);
      const extracted = await api.answers(id);
      setAnswers(extracted);
      setUploaded(true);
      if (result.answer_count !== extracted.length) setError(`Извлечено ${extracted.length} ответов из ${result.answer_count}. Проверьте статус извлечения перед проверкой.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить и нарезать PDF.");
    } finally {
      setWorking(false);
    }
  }

  async function startGrading() {
    setWorking(true);
    setError("");
    try {
      await api.grade(id);
      router.push(`/assignments/${id}/review`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось запустить проверку.");
      setWorking(false);
    }
  }

  const firstCrop = answers.find((answer) => answer.crop_data_url || answer.crop_url);
  const cropSource = firstCrop?.crop_data_url || firstCrop?.crop_url || undefined;

  return <AppShell>
    <div className="breadcrumbs-inline"><Link href="/assignments">Задания</Link><span>/</span><Link href={`/assignments/${id}/template`}>{assignment?.title ?? "Задание"}</Link><span>/</span><span>Загрузить работы</span></div>
    <section className="page-heading compact-heading"><div><div className="eyebrow">ШАГ 2 ИЗ 3 · РАБОТЫ</div><h1>Загрузить сканы</h1><p className="heading-subtitle">Один студент на страницу. Используйте тот же шаблон и масштаб, что и в бланке Forma.</p></div></section>
    {error && <div className="notice error-notice"><AlertTriangle size={16} />{error}</div>}
    {!uploaded ? <section className="upload-workspace">
      <label className={`dropzone ${file ? "has-file" : ""}`}>
        <input type="file" accept="application/pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} onDragOver={(event) => event.preventDefault()} onDrop={(event) => {
          event.preventDefault();
          const dropped = event.dataTransfer.files[0];
          if (dropped) {
            if (dropped.type !== "application/pdf") setError("Выберите файл PDF.");
            else { setError(""); setFile(dropped); }
          }
        }} />
        <span className="dropzone-icon"><FileUp size={22} /></span>
        <strong>{file ? file.name : "Перетащите PDF сюда или выберите файл"}</strong>
        <span>{file ? `${(file.size / 1024 / 1024).toFixed(1)} МБ` : "PDF · До 30 МБ · A4, одна работа на страницу"}</span>
        {!file && <span className="button secondary"><Upload size={14} />Выбрать PDF</span>}
      </label>
      <div className="upload-instructions"><strong>Перед загрузкой</strong><ul><li>Страницы сканов соответствуют выбранному шаблону.</li><li>Страницы ориентированы одинаково и расположены ровно.</li><li>На каждой странице одна работа; Forma присвоит анонимные номера.</li></ul></div>
      <div className="upload-actions"><Link href={`/assignments/${id}/template`} className="back-link"><ArrowLeft size={14} />Изменить шаблон</Link><button className="button primary" disabled={!file || working} onClick={() => void upload()}>{working ? <><LoaderCircle className="spin-icon" size={15} />Извлекаем ответы…</> : "Загрузить и проверить кропы"}</button></div>
    </section> : <section className="alignment-preview">
      <div className="alignment-header"><div className="alignment-success"><span><Check size={15} /></span><div><strong>Кропы извлечены</strong><small>{answers.length} ответов · {file?.name}</small></div></div><span className="warning-chip"><AlertTriangle size={14} />Проверьте совмещение</span></div>
      {cropSource ? <div className="first-crop-preview"><div><ProtectedImage url={cropSource} alt="Предпросмотр извлечённого ответа" /></div><section><h2>Предпросмотр первого ответа</h2><p>До запуска Gemini проверьте, что выделенная область содержит полное решение и не захватывает соседнюю задачу.</p><p className="muted">Если рамка смещена, вернитесь к шаблону и измените координаты. Повторная загрузка создаст новый набор кропов.</p></section></div> : <div className="notice error-notice">Не удалось найти изображения кропов. Вернитесь к загрузке и повторите извлечение.</div>}
      <div className="upload-actions"><button className="button secondary" onClick={() => { setUploaded(false); setAnswers([]); }}>Загрузить другой PDF</button><button className="button primary" disabled={working || !cropSource} onClick={() => void startGrading()}>{working ? "Запускаем проверку…" : "Подтвердить кропы и начать проверку"}</button></div>
    </section>}
  </AppShell>;
}
