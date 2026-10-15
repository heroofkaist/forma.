"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Download, FileText } from "lucide-react";
import { AppShell, StatusLabel } from "../../../../components/app-shell";
import { api, downloadAuthenticatedFile } from "../../../../lib/api";
import type { Answer, Assignment, Grading } from "../../../../lib/types";

export default function ResultsPage() {
  const { id } = useParams<{ id: string }>();
  const [assignment, setAssignment] = useState<Assignment | null>(null);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [statusFilter, setStatusFilter] = useState("all");
  const [ascending, setAscending] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.assignment(id), api.answers(id)]).then(([task, results]) => { setAssignment(task); setAnswers(results); }).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось загрузить результаты."));
  }, [id]);

  const students = useMemo(() => {
    const map = new Map<string, Answer[]>();
    answers.forEach((answer) => map.set(answer.anonymous_student_id, [...(map.get(answer.anonymous_student_id) ?? []), answer]));
    return [...map.entries()].map(([student, studentAnswers]) => {
      const approved = studentAnswers.filter((answer) => answer.status === "approved");
      const total = approved.reduce((sum, answer) => sum + teacherTotal(answer.grading ?? answer.ai_result_json), 0);
      return { student, answers: studentAnswers, total, approved: approved.length, allApproved: !!assignment && approved.length === assignment.questions.length };
    }).filter((row) => statusFilter === "all" || (statusFilter === "approved" ? row.allApproved : !row.allApproved)).sort((a, b) => ascending ? a.total - b.total : b.total - a.total);
  }, [answers, assignment, statusFilter, ascending]);

  const totalMax = assignment?.questions.reduce((sum, question) => sum + question.maximum_points, 0) ?? 0;
  const completed = students.filter((student) => student.allApproved).length;
  const resultColumns = `minmax(140px,1.4fr) repeat(${assignment?.questions.length ?? 3}, minmax(90px,1fr)) minmax(78px,.8fr) minmax(110px,.9fr)`;

  return <AppShell>
    <div className="review-topline"><div className="breadcrumbs-inline"><Link href="/assignments">Задания</Link><span>/</span><Link href={`/assignments/${id}/review`}>{assignment?.title ?? "Задание"}</Link><span>/</span><span>Результаты</span></div><Link className="quiet-button" href={`/assignments/${id}/review`}>К проверке</Link></div>
    <section className="page-heading compact-heading"><div><div className="eyebrow">РЕЗУЛЬТАТЫ · {assignment?.subject === "Physics" ? "ФИЗИКА" : "МАТЕМАТИКА"}</div><h1>{assignment?.title ?? "Результаты"}</h1><p className="heading-subtitle">{completed} из {students.length} работ полностью утверждены. Неутверждённые предложения ИИ не включаются в итоговый балл.</p></div><button className="button primary" onClick={() => void downloadAuthenticatedFile(api.exportPath(id), `${id}-results.csv`).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось скачать экспорт."))}><Download size={15} />Экспорт CSV</button></section>
    {error && <div className="notice error-notice">{error}</div>}
    <div className="results-toolbar"><label className="filter-select">Показывать<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">Все работы</option><option value="approved">Утверждённые</option><option value="pending">Не завершённые</option></select></label><button className="quiet-button" onClick={() => setAscending(!ascending)}>{ascending ? <ArrowUp size={14} /> : <ArrowDown size={14} />}Итоговый балл</button></div>
    {students.length ? <div className="results-table">
      <div className="results-row results-head" style={{ gridTemplateColumns: resultColumns }}><span>СТУДЕНТ</span>{assignment?.questions.map((question, index) => <span key={question.id}>ЗАДАЧА {index + 1}</span>)}<span>ИТОГО</span><span>СТАТУС</span></div>
      {students.map((student) => <div className="results-row" key={student.student} style={{ gridTemplateColumns: resultColumns }}>
        <strong className="student-id">{student.student}</strong>
        {assignment?.questions.map((question) => {
          const answer = student.answers.find((item) => item.question_id === question.id);
          const evaluated = answer?.grading ?? answer?.ai_result_json;
          return <span className="result-points" key={question.id}>{answer?.status === "approved" ? `${teacherTotal(evaluated)} / ${question.maximum_points}` : <span className="draft-points">Черновик · {teacherTotal(evaluated)} / {question.maximum_points}</span>}</span>;
        })}
        <strong className="total-points">{student.total} <small>/ {totalMax}</small></strong>
        <span className="result-status"><StatusLabel status={student.allApproved ? "approved" : "ready_for_review"} /><Link href={`/assignments/${id}/review?student=${encodeURIComponent(student.student)}`} title="Открыть работу"><FileText size={14} /></Link></span>
      </div>)}
    </div> : <div className="empty-state"><div className="empty-icon"><FileText size={18} /></div><h2>Пока нет загруженных работ</h2><p>Загрузите PDF, чтобы извлечь ответы и увидеть оценки.</p><Link className="button primary" href={`/assignments/${id}/upload`}>Загрузить работы</Link></div>}
    <div className="export-note"><strong>Экспорт включает только утверждённые оценки.</strong> Предложенные ИИ баллы остаются черновиками до подтверждения преподавателем.</div>
  </AppShell>;
}

function teacherTotal(grading?: Grading) {
  if (!grading) return 0;
  return grading.criteria_results.reduce((sum, criterion) => sum + (criterion.teacher_points ?? criterion.suggested_points), 0);
}
