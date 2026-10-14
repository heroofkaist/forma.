"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { AppShell } from "../../../components/app-shell";
import { api } from "../../../lib/api";
import type { Criterion, Question, Subject } from "../../../lib/types";

const makeQuestion = (index: number): Question => ({
  id: `q${index + 1}`,
  title: `Задача ${index + 1}`,
  statement: "",
  reference_solution: "",
  maximum_points: 1,
  criteria: [{ id: `q${index + 1}-c1`, criterion_id: "C1", description: "", maximum_points: 1 }],
});

export default function NewAssignmentPage() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [subject, setSubject] = useState<Subject>("Physics");
  const [questions, setQuestions] = useState<Question[]>([makeQuestion(0), makeQuestion(1)]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function editQuestion(index: number, patch: Partial<Question>) {
    setQuestions((items) => items.map((item, i) => i === index ? { ...item, ...patch } : item));
  }

  function editCriterion(qIndex: number, cIndex: number, patch: Partial<Criterion>) {
    setQuestions((items) => items.map((item, i) => i !== qIndex ? item : {
      ...item,
      criteria: item.criteria.map((criterion, j) => j === cIndex ? { ...criterion, ...patch } : criterion),
    }));
  }

  function addCriterion(qIndex: number) {
    const question = questions[qIndex];
    const id = `C${question.criteria.length + 1}`;
    editQuestion(qIndex, { criteria: [...question.criteria, { id: `${question.id}-${id}`, criterion_id: id, description: "", maximum_points: 1 }] });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (questions.some((question) => !question.statement.trim() || !question.reference_solution.trim() || question.criteria.some((criterion) => !criterion.description.trim()))) {
      setError("Заполните условие, эталонное решение и описание всех критериев.");
      return;
    }
    setSaving(true);
    try {
      const created = await api.createAssignment({
        title: title.trim(),
        subject,
        status: "active",
        questions: questions.map((question) => ({
          ...question,
          maximum_points: question.criteria.reduce((sum, criterion) => sum + criterion.maximum_points, 0),
        })),
        demo_mode: false,
      });
      router.push(`/assignments/${created.id}/template`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось создать задание.");
    } finally {
      setSaving(false);
    }
  }

  const total = questions.reduce((sum, question) => sum + question.criteria.reduce((qSum, criterion) => qSum + (Number(criterion.maximum_points) || 0), 0), 0);

  return <AppShell>
    <div className="breadcrumbs-inline"><Link href="/">Задания</Link><span>/</span><span>Новое задание</span></div>
    <section className="page-heading compact-heading"><div><div className="eyebrow">НОВОЕ ЗАДАНИЕ</div><h1>Создать проверочную</h1><p className="heading-subtitle">Задайте вопросы и рубрику. Предложенные ИИ оценки всегда утверждает преподаватель.</p></div></section>
    {error && <div className="notice error-notice">{error}</div>}
    <form onSubmit={submit} className="create-layout">
      <div className="create-main">
        <section className="form-section">
          <div className="section-heading"><span className="section-number">01</span><div><h2>Основное</h2><p>Название и предмет контрольной работы.</p></div></div>
          <label className="form-label">Название задания<input required maxLength={140} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Например, Динамика: контрольная работа" /></label>
          <label className="form-label">Предмет<select value={subject} onChange={(event) => setSubject(event.target.value as Subject)}><option value="Physics">Физика</option><option value="Mathematics">Математика</option></select></label>
        </section>
        <section className="form-section questions-section">
          <div className="section-heading"><span className="section-number">02</span><div><h2>Задачи и оценивание</h2><p>От двух до трёх задач. Баллы суммируются из критериев.</p></div></div>
          {questions.map((question, qIndex) => <article className="question-editor" key={question.id}>
            <div className="question-editor-heading"><strong>{question.title}</strong>{questions.length > 2 && <button type="button" className="icon-action" aria-label="Удалить вопрос" onClick={() => setQuestions((items) => items.filter((_, index) => index !== qIndex))}><Trash2 size={15} /></button>}</div>
            <label className="form-label">Условие задачи<textarea required rows={3} value={question.statement} onChange={(event) => editQuestion(qIndex, { statement: event.target.value })} placeholder="Введите условие задачи..." /></label>
            <label className="form-label">Эталонное решение<textarea required rows={3} value={question.reference_solution} onChange={(event) => editQuestion(qIndex, { reference_solution: event.target.value })} placeholder="Ключевые шаги решения и верный ответ..." /></label>
            <div className="rubric-table">
              <div className="rubric-head"><span>КРИТЕРИЙ</span><span>МАКС. БАЛЛ</span><span /></div>
              {question.criteria.map((criterion, cIndex) => <div className="rubric-row" key={criterion.id}>
                <label className="sr-only" htmlFor={`${criterion.id}-description`}>Описание критерия</label>
                <input id={`${criterion.id}-description`} value={criterion.description} onChange={(event) => editCriterion(qIndex, cIndex, { description: event.target.value })} placeholder={`${criterion.criterion_id} · Например, правильная проекция силы тяжести`} required />
                <input aria-label={`Максимальный балл ${criterion.criterion_id}`} type="number" min="0" max="100" step="0.5" value={criterion.maximum_points} onChange={(event) => editCriterion(qIndex, cIndex, { maximum_points: Number(event.target.value) })} />
                <button type="button" className="icon-action" aria-label={`Удалить ${criterion.criterion_id}`} disabled={question.criteria.length <= 1} onClick={() => editQuestion(qIndex, { criteria: question.criteria.filter((_, index) => index !== cIndex) })}><Trash2 size={14} /></button>
              </div>)}
              <button type="button" className="add-criterion" onClick={() => addCriterion(qIndex)}><Plus size={14} />Добавить критерий</button>
            </div>
          </article>)}
          {questions.length < 3 && <button type="button" className="add-question" onClick={() => setQuestions((items) => [...items, makeQuestion(items.length)])}><Plus size={15} />Добавить задачу</button>}
        </section>
      </div>
      <aside className="summary-panel">
        <div className="summary-heading">СВОДКА</div>
        <div className="summary-row"><span>Предмет</span><strong>{subject === "Physics" ? "Физика" : "Математика"}</strong></div>
        <div className="summary-row"><span>Количество задач</span><strong>{questions.length}</strong></div>
        <div className="summary-score"><span>Максимальный балл</span><strong>{total}</strong></div>
        <div className="summary-help">На следующем шаге настройте области ответа в бланке или используйте стандартный шаблон Forma.</div>
        <button className="button primary full-button" type="submit" disabled={saving || !title.trim()}>{saving ? "Сохраняем…" : "Продолжить к шаблону"}</button>
        <Link href="/" className="back-link"><ArrowLeft size={14} />Вернуться к заданиям</Link>
      </aside>
    </form>
  </AppShell>;
}
