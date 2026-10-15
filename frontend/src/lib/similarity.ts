import type { SimilarityReport } from "./academic";

export const similarityStates: Record<string, string> = {
  missing: "Отчёт недоступен. Сохранённого результата сравнения нет.",
  queued: "Сравнение ожидает обработки.", analyzing: "Сравнение выполняется.",
  failed: "Сравнение не завершилось. Результат недоступен.",
  insufficient_text: "Недостаточно читаемого текста для сравнения (нужно не менее 8 слов).",
  no_sources: "В выбранной области нет подходящих работ других авторов для сравнения.",
  disabled: "Сравнение отключено для этого задания.",
  incomplete: "Сохранённый результат неполон. Процент совпадений недоступен.",
  completed: "Сравнение завершено",
};
export function similarityPercent(report: SimilarityReport): string {
  return report.analysis_status === "completed" && report.matched_text_ratio !== null
    ? `${Math.round(report.matched_text_ratio * 100)}%` : "—";
}
export function codePointPassage(text: string, start: number, end: number): [string, string, string] {
  const points = Array.from(text);
  return [points.slice(0, start).join(""), points.slice(start, end).join(""), points.slice(end).join("")];
}
export function normalizeReport(raw: Record<string, unknown>): SimilarityReport {
  const evidence = Array.isArray(raw.evidence) ? raw.evidence as Record<string, unknown>[] : [];
  const ratio = raw.match_ratio;
  const eligible = raw.eligible_token_count;
  const matched = raw.matched_token_count;
  const validEvidence = evidence.every(item => {
    const source = item.source_offsets as {start?: unknown; end?: unknown} | undefined;
    const candidate = item.candidate_offsets as {start?: unknown; end?: unknown} | undefined;
    return source && candidate && Number.isInteger(source.start) && Number.isInteger(source.end) &&
      Number.isInteger(candidate.start) && Number.isInteger(candidate.end) &&
      (source.start as number) >= 0 && (source.end as number) > (source.start as number) &&
      (candidate.start as number) >= 0 && (candidate.end as number) > (candidate.start as number) &&
      typeof raw.extracted_text === "string" && Array.from(raw.extracted_text).slice(source.start as number, source.end as number).join("") === item.source_excerpt &&
      typeof item.candidate_excerpt === "string" && item.candidate_excerpt.length > 0;
  });
  const valid = validEvidence && raw.analysis_status === "completed" && typeof ratio === "number" && Number.isFinite(ratio) && ratio >= 0 && ratio <= 1 &&
    typeof eligible === "number" && eligible >= 8 && typeof matched === "number" && matched >= 0 && matched <= eligible &&
    Math.abs(ratio - matched / eligible) <= 0.000001 && typeof raw.extracted_text === "string" && Boolean(raw.extracted_text.trim()) &&
    (matched === 0 ? evidence.length === 0 : evidence.length > 0);
  const reportId = String(raw.id ?? "");
  return {
    id: reportId, submission_id: String(raw.submission_id ?? ""),
    analysis_status: valid ? "completed" : raw.analysis_status === "completed" ? "incomplete" : String(raw.analysis_status ?? "missing"),
    matched_text_ratio: valid ? ratio : null,
    analysis_scope: String(raw.match_scope ?? ""), created_at: typeof raw.created_at === "string" ? raw.created_at : undefined,
    extracted_text: String(raw.extracted_text ?? ""), eligible_token_count: typeof eligible === "number" ? eligible : undefined,
    review_status: String(raw.review_status ?? "unreviewed"), teacher_notes: String(raw.teacher_notes ?? ""),
    course: String(raw.course_name ?? raw.course_code ?? ""), assignment: String(raw.assignment_title ?? ""),
    academic_year: String(raw.academic_year ?? ""), document_title: String(raw.document_title ?? ""),
    matches: valid ? evidence.map((item, index) => {
      const source = item.source_offsets as { start: number; end: number };
      const candidate = item.candidate_offsets as { start: number; end: number };
      return {id: `${reportId}-${index}`, report_id: reportId, source_submission_id: String(raw.candidate_submission_id ?? ""),
        source_title: String(raw.source_title ?? "Архивная работа"), source_course: String(raw.source_course ?? ""),
        source_assignment: String(raw.source_assignment ?? ""), source_term: String(raw.source_term ?? ""),
        matched_excerpt: String(item.candidate_excerpt ?? ""), source_excerpt: String(item.source_excerpt ?? ""),
        current_text_start: source.start, current_text_end: source.end, source_text_start: candidate.start, source_text_end: candidate.end,
        similarity_method: "Сравнение последовательностей слов"};
    }) : [],
  };
}
export type SimilarityResult = { analysis: SimilarityReport; reports: SimilarityReport[] };
export function normalizeSimilarityResult(raw: { submission_id: string; analysis?: Record<string, unknown>; items: Record<string, unknown>[] }): SimilarityResult {
  const reports = raw.items.map(normalizeReport);
  const summary = raw.analysis ?? {submission_id: raw.submission_id, analysis_status: "missing"};
  const analysis = normalizeReport(summary);
  const hasReceipt = summary.analysis_status === "completed" && typeof summary.eligible_token_count === "number" && summary.eligible_token_count >= 8 &&
    typeof summary.match_ratio === "number" && Number.isFinite(summary.match_ratio) && summary.match_ratio >= 0 && summary.match_ratio <= 1 &&
    typeof summary.extracted_text === "string" && Boolean(summary.extracted_text.trim());
  const valid = hasReceipt && reports.every(r => r.analysis_status === "completed") &&
    (reports.length > 0 && summary.match_ratio === Math.max(...reports.map(r => r.matched_text_ratio ?? -1)) || (typeof summary.candidate_count === "number" && summary.candidate_count > 0 && summary.match_ratio === 0));
  analysis.analysis_status = valid ? "completed" : summary.analysis_status === "completed" ? "incomplete" : String(summary.analysis_status ?? "missing");
  analysis.matched_text_ratio = valid ? summary.match_ratio as number : null;
  analysis.matches = valid ? reports.flatMap(r => r.matches) : [];
  return {analysis, reports};
}
