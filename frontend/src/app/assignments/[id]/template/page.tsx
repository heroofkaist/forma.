"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { PointerEvent, useEffect, useRef, useState } from "react";
import { ArrowLeft, Check, Printer, RotateCw, Upload } from "lucide-react";
import { AppShell } from "../../../../components/app-shell";
import { API_URL, api, authenticatedFetch } from "../../../../lib/api";
import type { Assignment, Question, Region } from "../../../../lib/types";

type Preview = { preview_data_url: string; page_count: number; width: number; height: number };

const defaultRegions = (questions: Question[]): Record<string, Region> => Object.fromEntries(questions.map((question, index) => {
  const height = 0.82 / questions.length;
  return [question.id, { x1: 0.08, x2: 0.92, y1: 0.08 + index * height, y2: 0.08 + (index + 1) * height - 0.035 }];
}));

export default function TemplateEditorPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [assignment, setAssignment] = useState<Assignment | null>(null);
  const [regions, setRegions] = useState<Record<string, Region>>({});
  const [activeId, setActiveId] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [rotation, setRotation] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const stage = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; original: Region } | null>(null);

  useEffect(() => {
    api.assignment(id).then((data) => {
      setAssignment(data);
      setActiveId(data.questions[0]?.id ?? "");
      const existing = Object.fromEntries(data.questions.filter((question) => question.region).map((question) => [question.id, question.region!]));
      setRegions({ ...defaultRegions(data.questions), ...existing });
    }).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось загрузить задание."));
  }, [id]);

  async function onTemplatePdf(file: File) {
    const body = new FormData();
    body.append("file", file);
    try {
      const response = await authenticatedFetch(`${API_URL}/api/pdf/preview`, { method: "POST", body });
      if (!response.ok) throw new Error(await errorText(response));
      setPreview(await response.json() as Preview);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось открыть PDF.");
    }
  }

  function getPoint(event: PointerEvent<HTMLDivElement>) {
    const rect = stage.current!.getBoundingClientRect();
    return { x: Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)), y: Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height)) };
  }

  function startMove(event: PointerEvent<HTMLButtonElement>, questionId: string) {
    if (!stage.current) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { ...getPoint(event as unknown as PointerEvent<HTMLDivElement>), original: regions[questionId] };
    setActiveId(questionId);
  }

  function moveRegion(event: PointerEvent<HTMLButtonElement>, questionId: string) {
    if (!drag.current) return;
    const point = getPoint(event as unknown as PointerEvent<HTMLDivElement>);
    const dx = point.x - drag.current.x;
    const dy = point.y - drag.current.y;
    const original = drag.current.original;
    const width = original.x2 - original.x1;
    const height = original.y2 - original.y1;
    const x1 = Math.max(0, Math.min(1 - width, original.x1 + dx));
    const y1 = Math.max(0, Math.min(1 - height, original.y1 + dy));
    setRegions((items) => ({ ...items, [questionId]: { x1, y1, x2: x1 + width, y2: y1 + height } }));
  }

  function stopMove() { drag.current = null; }

  function editRegion(field: keyof Region, raw: string) {
    const value = Math.max(0, Math.min(1, Number(raw) || 0));
    const current = regions[activeId];
    if (!current) return;
    const next = { ...current, [field]: value };
    if (next.x1 >= next.x2 || next.y1 >= next.y2) {
      setError("Координаты x1/y1 должны быть меньше x2/y2.");
      return;
    }
    setError("");
    setRegions((items) => ({ ...items, [activeId]: next }));
  }

  async function saveTemplate() {
    if (!assignment) return;
    const boxes = assignment.questions.map((question) => regions[question.id]);
    if (boxes.some((box) => !box || box.x1 >= box.x2 || box.y1 >= box.y2)) {
      setError("У каждого вопроса должна быть непустая область ответа в пределах страницы.");
      return;
    }
    const overlaps = boxes.some((box, index) => boxes.slice(index + 1).some((other) =>
      Math.max(box.x1, other.x1) < Math.min(box.x2, other.x2)
      && Math.max(box.y1, other.y1) < Math.min(box.y2, other.y2)));
    if (overlaps) {
      setError("Области ответов пересекаются. Измените координаты, чтобы разделить задачи.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await api.saveTemplate(id, assignment.questions.map((question) => ({ question_id: question.id, region: regions[question.id] })), rotation);
      router.push(`/assignments/${id}/upload`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось сохранить шаблон.");
    } finally {
      setSaving(false);
    }
  }

  const activeQuestion = assignment?.questions.find((question) => question.id === activeId);
  const activeRegion = regions[activeId];
  return <AppShell>
    <div className="breadcrumbs-inline"><Link href="/assignments">Задания</Link><span>/</span><Link href={`/assignments/${id}/review`}>{assignment?.title ?? "Задание"}</Link><span>/</span><span>Шаблон</span></div>
    <section className="page-heading compact-heading"><div><div className="eyebrow">ШАГ 1 ИЗ 3 · БЛАНК</div><h1>Области ответов</h1><p className="heading-subtitle">Распечатайте шаблон Forma или загрузите свой. Сканы студентов должны совпадать с этим бланком.</p></div><div className="heading-actions"><button className="button secondary" onClick={() => window.print()}><Printer size={15} />Печать бланка</button><label className="button secondary file-button"><Upload size={15} />Загрузить пустой PDF<input type="file" accept="application/pdf" onChange={(event) => event.target.files?.[0] && onTemplatePdf(event.target.files[0])} /></label></div></section>
    {error && <div className="notice error-notice">{error}</div>}
    {assignment && <div className="template-editor-layout">
      <section className="template-canvas-panel">
        <div className="canvas-toolbar"><strong>{preview ? "Пустой бланк · страница 1" : "Предпросмотр печатного бланка"}</strong><div className="canvas-tools"><button className="quiet-button" onClick={() => setRotation((value) => (value + 90) % 360)} title="Поворот сканов студентов">{rotation === 0 ? <RotateCw size={14} /> : <><RotateCw size={14} />{rotation}°</>}</button><button className="quiet-button" onClick={() => { setPreview(null); setRotation(0); }}>Сбросить</button></div></div>
        {preview ? <div className="template-stage-wrap"><div className="template-stage" ref={stage} style={{ backgroundImage: `url(${preview.preview_data_url})` }}>
          {assignment.questions.map((question) => {
            const box = regions[question.id];
            return <button key={question.id} className={`template-region ${question.id === activeId ? "is-active" : ""}`} style={{ left: `${box.x1 * 100}%`, top: `${box.y1 * 100}%`, width: `${(box.x2 - box.x1) * 100}%`, height: `${(box.y2 - box.y1) * 100}%` }} onPointerDown={(event) => startMove(event, question.id)} onPointerMove={(event) => moveRegion(event, question.id)} onPointerUp={stopMove} onClick={() => setActiveId(question.id)}>{question.title}</button>;
          })}
        </div></div> : <div className="print-sheet">
          <div className="print-brand">FORMA <span>·</span> {assignment.subject === "Physics" ? "ФИЗИКА" : "МАТЕМАТИКА"}</div><h2>{assignment.title}</h2><div className="student-name-line">Фамилия, имя <span /></div>
          {assignment.questions.map((question, index) => <article className="print-question" key={question.id}><strong>{index + 1}. {question.statement}</strong><div className="print-answer-box"><small>РЕШЕНИЕ</small></div></article>)}
        </div>}
        <div className="canvas-hint">{preview && Math.abs(preview.width / preview.height - 210 / 297) > 0.025 ? <strong>Размер загруженной страницы отличается от A4 portrait.</strong> : null} Области сохраняются в координатах страницы. Поворот применяется к загруженным работам при нарезке.</div>
      </section>
      <aside className="template-settings">
        <div className="panel-title"><strong>Зоны вопросов</strong><span>{assignment.questions.length} / 3</span></div>
        <div className="template-question-list">{assignment.questions.map((question, index) => <button className={`template-question ${question.id === activeId ? "selected" : ""}`} key={question.id} onClick={() => setActiveId(question.id)}><span className="question-n">Q{index + 1}</span><span><strong>{question.title}</strong><small>{question.maximum_points} баллов</small></span></button>)}</div>
        {activeQuestion && activeRegion && <div className="region-settings"><div className="region-label">{activeQuestion.title} · область ответа</div><div className="coordinate-grid">{(["x1", "y1", "x2", "y2"] as const).map((field) => <label key={field}>{field}<input type="number" min="0" max="1" step="0.01" value={activeRegion[field]} onChange={(event) => editRegion(field, event.target.value)} /></label>)}</div><div className="coordinate-note">Координаты нормированы от 0 до 1. Перемещайте рамку на загруженном бланке или задайте числа вручную.</div></div>}
        <div className="alignment-warning"><strong>Важно</strong><span>Используйте тот же размер, ориентацию и расположение бланка для всех студентов.</span></div>
        <div className="template-footer"><Link className="back-link" href={`/assignments/${id}/review`}><ArrowLeft size={14} />Назад</Link><button className="button primary" onClick={() => void saveTemplate()} disabled={saving}>{saving ? "Сохраняем…" : <><Check size={15} />Сохранить шаблон</>}</button></div>
      </aside>
    </div>}
  </AppShell>;
}

async function errorText(response: Response) {
  const data = await response.json().catch(() => null) as { detail?: string } | null;
  return data?.detail ?? `Ошибка сервера (${response.status})`;
}
