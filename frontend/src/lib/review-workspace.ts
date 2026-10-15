/** Server contracts and a subject-independent view model. No scoring authority here. */
export type Finding = "strength" | "concern" | "mixed" | "insufficient_evidence";
export type Evidence = { section_id: string; page_number: number; quote: string };
export type Criterion = { question_id: string; criterion_id: string; description: string; maximum_points: number; performance_descriptions?: string; feedback_requirements?: string; weight?: number | null; insight_tag?: string };
export type Rubric = { category: string; instructions: string; reference_material: string; criteria: Criterion[] };
export type Suggestion = { question_id: string; criterion_id: string; proposed_score: number | null; rationale: string; evidence: Evidence[]; interpretation: string; finding: Finding; suggested_improvement: string; missing_evidence: string[]; uncertainty: string[]; verification_status: "needs_review" };
export type Decision = { question_id: string; criterion_id: string; action: "accepted" | "rejected" | "deferred"; points: number | null; feedback: string; finding: Finding; confirmed?: boolean; overall_feedback?: string };
export type AssessmentVersion = { id: string; rubric: { id: string; spec: Rubric }; result: { criteria: Suggestion[] }; interpretation_id: string; correction_id: string | null; decisions: { id: string; reviewer: string; created_at: string; decisions: Decision[]; review_id: string | null }[]; source: { sections: { id: string; evidence_kind: string; readability: string }[] } };
export type AssessmentResponse = { items: AssessmentVersion[]; jobs: { id: string; status: string; error: string }[]; supported: boolean };
export type Score = { question_id: string; criterion_id: string; points: number | null; comment: string; confirmed?: boolean };
export type ManualReview = { id: string; criteria: Score[]; feedback: string; created_at: string; reviewer: string };
export type ReviewResponse = { submission_id: string; assignment_id: string; title: string; assignment_type?: string; instructions?: string; submitted_at?: string; student_name: string; file_name: string; file_type: string; maximum_score: number; questions: { id: string; title: string; statement?: string; criteria: { criterion_id: string; description: string; maximum_points: number }[] }[]; structure: { pages: { number: number; unit: string; text: string }[]; warnings: string[] } | null; reviews: ManualReview[]; published_grade: { points: number; maximum_score?: number; published_at: string; review_id?: string | null } | null };
export type CriterionView = Criterion & { key: string; suggestion: Suggestion | null; saved: Decision | null };
export type EditorValue = { action: Decision["action"] | "unreviewed"; points: string; feedback: string; finding: Finding };
export type ReviewEditor = { criteria: Record<string, EditorValue>; feedback: string; mode: "assisted" | "manual" };
export const criterionKey = (question: string, criterion: string) => JSON.stringify([question, criterion]);
export const categoryLabels: Record<string, string> = { problem_set: "Задачи и расчёты", essay: "Эссе", lab_report: "Лабораторный отчёт", presentation: "Презентация", research_report: "Исследовательская работа", programming: "Программирование", homework: "Учебная работа", general: "Учебная работа" };
export const findingLabels: Record<Finding, string> = { strength: "Сильная сторона", concern: "Есть замечания", mixed: "Смешанный результат", insufficient_evidence: "Недостаточно данных" };
export const decisionLabels = { unreviewed: "Не проверено", accepted: "Проверено", rejected: "Предложение отклонено", deferred: "Отложено" };

export function reviewCriteria(data: ReviewResponse, version?: AssessmentVersion): CriterionView[] {
  return data.questions.flatMap(q => q.criteria.map(c => {
    const approved = version?.rubric.spec.criteria.find(r => r.question_id === q.id && r.criterion_id === c.criterion_id && r.maximum_points === c.maximum_points);
    return { ...c, ...(approved ?? {}), question_id: q.id, key: criterionKey(q.id, c.criterion_id),
      suggestion: approved ? version?.result.criteria.find(r => r.question_id === q.id && r.criterion_id === c.criterion_id) ?? null : null,
      saved: approved ? version?.decisions[0]?.decisions.find(d => d.question_id === q.id && d.criterion_id === c.criterion_id) ?? null : null };
  }));
}

export function initialEditor(data: ReviewResponse, version?: AssessmentVersion): ReviewEditor {
  const decisionReview = version?.decisions[0];
  const manual = data.reviews[0];
  const mode = !version || (manual && manual.id !== decisionReview?.review_id && new Date(manual.created_at).getTime() > new Date(decisionReview?.created_at ?? 0).getTime()) ? "manual" : "assisted";
  return { mode, feedback: mode === "assisted" ? decisionReview?.decisions[0]?.overall_feedback ?? (decisionReview?.review_id === manual?.id ? manual?.feedback : "") ?? "" : manual?.feedback ?? "",
    criteria: Object.fromEntries(reviewCriteria(data, version).map(c => {
      const score = manual?.criteria.find(s => s.question_id === c.question_id && s.criterion_id === c.criterion_id);
      const saved = c.saved;
      return [c.key, { action: mode === "manual" ? "unreviewed" : saved?.action ?? "unreviewed",
        // Never initialize a teacher score or feedback from an AI proposal.
        points: String((mode === "manual" ? score?.points : saved?.points) ?? ""),
        feedback: (mode === "manual" ? score?.comment : saved?.feedback) ?? "", finding: saved?.finding ?? c.suggestion?.finding ?? "insufficient_evidence" }];
    })) };
}

export function scoreError(value: string, maximum: number): string | null {
  if (!value.trim()) return null;
  const number = Number(value);
  return !Number.isFinite(number) || number < 0 || number > maximum ? `Введите балл от 0 до ${maximum}.` : null;
}
export function editorErrors(criteria: CriterionView[], editor: ReviewEditor): string[] {
  return criteria.flatMap(c => { const v = editor.criteria[c.key]; const error = scoreError(v.points, c.maximum_points);
    return error ? [error] : editor.mode === "assisted" && v.action !== "accepted" && v.points !== "" ? ["Баллы доступны для принятого решения. Для независимой оценки выберите ручную проверку."] : []; });
}
export function completeScores(criteria: CriterionView[], editor: ReviewEditor): boolean {
  return criteria.length > 0 && editorErrors(criteria, editor).length === 0 && criteria.every(c => editor.criteria[c.key].points.trim() !== "" && (editor.mode === "manual" || editor.criteria[c.key].action === "accepted"));
}
export function decisionsPayload(criteria: CriterionView[], editor: ReviewEditor): Decision[] {
  return criteria.map(c => { const v = editor.criteria[c.key]; return { question_id: c.question_id, criterion_id: c.criterion_id,
    action: v.action === "unreviewed" ? "deferred" : v.action, points: v.points.trim() === "" ? null : Number(v.points), feedback: v.feedback, finding: v.finding }; });
}
export function manualPayload(criteria: CriterionView[], editor: ReviewEditor): Score[] {
  return criteria.map(c => ({ question_id: c.question_id, criterion_id: c.criterion_id, points: editor.criteria[c.key].points.trim() === "" ? null : Number(editor.criteria[c.key].points), comment: editor.criteria[c.key].feedback }));
}
export function canPublish(data: ReviewResponse): boolean {
  const review = data.reviews[0]; if (!review || !review.criteria.length) return false;
  const criteria = reviewCriteria(data); const keys = new Set(review.criteria.map(s => criterionKey(s.question_id, s.criterion_id)));
  return keys.size === criteria.length && review.criteria.length === criteria.length && criteria.every(c => {
    const score = review.criteria.find(s => criterionKey(s.question_id, s.criterion_id) === c.key);
    return score?.points != null && score.confirmed !== false && !scoreError(String(score.points), c.maximum_points);
  }) && review.criteria.reduce((sum, c) => sum + (c.points ?? 0), 0) <= data.maximum_score;
}
export function publicationReady(data: ReviewResponse, version: AssessmentVersion | undefined, mode: ReviewEditor['mode']): boolean {
  if (!canPublish(data)) return false;
  if (mode === 'manual') return true;
  const decision = version?.decisions[0];
  return !!decision?.review_id && decision.review_id === data.reviews[0].id && decision.decisions.every(d => d.confirmed !== false);
}
export function shortSummary(suggestion: Suggestion | null): string {
  if (!suggestion) return "Оцените критерий по оригиналу работы.";
  const text = suggestion.interpretation.trim();
  if (!text) return findingLabels[suggestion.finding] + ". Сверьте с оригиналом.";
  return text.length > 155 ? text.slice(0, 152) + "…" : text;
}

export type SavedReviewState = "unreviewed" | "draft" | "confirmed" | "published";
export function editorSavedState(data: ReviewResponse, version: AssessmentVersion | undefined, mode: ReviewEditor['mode']): SavedReviewState {
  const decision = version?.decisions[0];
  const manual = mode === 'manual' ? data.reviews[0] : data.reviews.find(r => r.id === decision?.review_id);
  if (manual && manual.id === data.published_grade?.review_id) return 'published';
  if (mode === 'assisted' && decision) return decision.decisions.some(d => d.confirmed === false) ? 'draft' : 'confirmed';
  if (manual) return manual.criteria.some(c => c.confirmed === false || c.points === null) ? 'draft' : 'confirmed';
  return 'unreviewed';
}
export const savedReviewLabels: Record<SavedReviewState, string> = {
  unreviewed: 'Не оценено', draft: 'Сохранённый черновик', confirmed: 'Подтверждено', published: 'Опубликовано',
};
