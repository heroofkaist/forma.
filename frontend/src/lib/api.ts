import type { Answer, Assignment, CriterionResult, Grading, Question, Region } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = typeof body?.detail === "string"
      ? body.detail
      : Array.isArray(body?.detail)
        ? body.detail.map((item) => typeof item === "object" && item !== null && "msg" in item ? String(item.msg) : String(item)).join("; ")
        : `Ошибка сервера (${response.status})`;
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

function normalizeAssignment(value: unknown): Assignment {
  const raw = value as Assignment;
  const questions = (raw.questions ?? []).map((question) => ({
    ...question,
    title: question.title || question.label || "Задача",
    criteria: question.criteria ?? [],
  })) as Question[];
  const subject = String(raw.subject ?? "").toLocaleLowerCase();
  return { ...raw, subject: subject === "physics" || subject === "физика" ? "Physics" : "Mathematics", questions };
}

function normalizeGrading(answer: Record<string, unknown>): Grading | undefined {
  const raw = (answer.grading ?? answer.ai_result_json) as Record<string, unknown> | null;
  if (!raw) return undefined;
  const sourceCriteria = Array.isArray(raw.criteria_results) ? raw.criteria_results as Record<string, unknown>[] : [];
  const original = answer.ai_result_json as Record<string, unknown> | null;
  const suggestedCriteria = original && Array.isArray(original.criteria_results)
    ? original.criteria_results as Record<string, unknown>[]
    : sourceCriteria;
  const reviewStatus = String(answer.review_status ?? "");
  const hasTeacherReview = ["reviewed", "reopened", "approved"].includes(reviewStatus) || answer.approved === true;
  const notes = Array.isArray(raw.transcription_notes) ? raw.transcription_notes.map(String) : [];
  const notesText = notes.join(" ");
  const impliedReadability = /не является транскрипц|решение не оценивалось/i.test(notesText)
    ? "unreadable"
    : /unreadable|unclear|illegible|obscured|неразборч|нечитаем|не удалось прочитать/i.test(notesText)
      ? "partially_readable"
      : raw.transcribed_latex ? "readable" : "unreadable";
  const criteria: CriterionResult[] = sourceCriteria.map((criterion) => {
    const suggestion = suggestedCriteria.find((item) => item.criterion_id === criterion.criterion_id) ?? criterion;
    const points = Number(criterion.points_awarded ?? criterion.suggested_points ?? 0);
    const suggestedPoints = Number(suggestion.points_awarded ?? suggestion.suggested_points ?? points);
    const evidence = criterion.evidence_from_solution ?? criterion.evidence;
    return {
      criterion_id: String(criterion.criterion_id ?? ""),
      status: (criterion.status ?? (criterion.passed ? "awarded" : "not_awarded")) as CriterionResult["status"],
      suggested_points: suggestedPoints,
      teacher_points: hasTeacherReview ? points : null,
      explanation: String(criterion.comment ?? criterion.explanation ?? ""),
      evidence_from_solution: Array.isArray(evidence) ? evidence.map(String).join("\n") : String(evidence ?? ""),
      manually_overridden: hasTeacherReview && points !== suggestedPoints,
    };
  });
  const uncertain = criteria.some((criterion) => criterion.status === "uncertain");
  return {
    transcribed_latex: String(raw.transcribed_latex ?? answer.transcription ?? ""),
    transcription_notes: notes.length ? notes.join("\n") : String(raw.transcription_notes ?? ""),
    transcription_status: (raw.transcription_status ?? impliedReadability) as Grading["transcription_status"],
    criteria_results: criteria,
    overall_feedback: String(raw.overall_feedback ?? answer.feedback ?? ""),
    requires_human_attention: Boolean(raw.requires_human_attention ?? uncertain),
    attention_reasons: Array.isArray(raw.attention_reasons) ? raw.attention_reasons.map(String) : [],
    uncertainty: Number(raw.uncertainty ?? answer.uncertainty ?? 0),
    total_points: Number(raw.total_score ?? answer.suggested_points ?? answer.points ?? 0),
    approved_total: answer.approved === true ? Number(answer.points ?? 0) : null,
    teacher_comment: String(answer.teacher_comment ?? raw.teacher_comment ?? ""),
    is_demo_output: Boolean(raw.is_demo_output ?? answer.is_demo_output),
  };
}

function normalizeAnswer(value: unknown): Answer {
  const raw = value as Record<string, unknown>;
  const reviewStatus = String(raw.review_status ?? "");
  const sourceStatus = String(raw.status ?? "pending");
  const grading = normalizeGrading(raw);
  const needsAttention = Boolean(grading?.requires_human_attention || grading?.criteria_results.some((item) => item.status === "uncertain"));
  const status: Answer["status"] = raw.approved === true || reviewStatus === "approved" ? "approved"
    : sourceStatus === "failed" ? "failed"
      : sourceStatus === "grading" || sourceStatus === "queued" ? "processing"
        : sourceStatus === "completed" ? needsAttention ? "needs_attention" : "ready_for_review"
          : reviewStatus === "reopened" ? "ready_for_review"
            : sourceStatus as Answer["status"];
  return {
    ...(raw as unknown as Answer),
    anonymous_student_id: String(raw.anonymous_student_id ?? "Student"),
    status,
    crop_url: typeof raw.crop_url === "string" ? raw.crop_url : undefined,
    source_page_url: typeof raw.source_page_url === "string" ? raw.source_page_url : undefined,
    grading,
    ai_result_json: grading,
  };
}

export const api = {
  assignments: async () => {
    const result = await request<{ items?: unknown[] } | unknown[]>("/assignments");
    const items = Array.isArray(result) ? result : result.items ?? [];
    return items.map(normalizeAssignment);
  },
  assignment: async (id: string) => normalizeAssignment(await request<unknown>(`/assignments/${id}`)),
  deleteAssignment: async (id: string) => {
    const response = await fetch(`${API_URL}/assignments/${id}`, { method: "DELETE" });
    if (!response.ok) throw new Error(`Не удалось удалить задание (${response.status}).`);
  },
  createAssignment: async (payload: Omit<Assignment, "id">) =>
    normalizeAssignment(await request<unknown>("/assignments", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })),
  saveTemplate: async (id: string, regions: Array<{ question_id: string; region: Region }>, rotation = 0) =>
    normalizeAssignment(await request<unknown>(`/assignments/${id}/template`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ regions: regions.map(({ question_id, region }) => ({ question_id, ...region })), rotation }) })),
  upload: (id: string, file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<{ submission_count: number; answer_count: number; answers: unknown[] }>(`/assignments/${id}/submissions`, { method: "POST", body: data });
  },
  grade: (id: string) => request<{ status: string; queued?: number }>(`/assignments/${id}/grade`, { method: "POST" }),
  progress: (id: string) => request<{ total: number; completed?: number; evaluated?: number; failed?: number; queued?: number; grading?: number; progress?: number; status?: string; statuses?: Record<string, number> }>(`/assignments/${id}/progress`),
  answers: async (id: string) => {
    const result = await request<{ items?: unknown[] } | unknown[]>(`/assignments/${id}/answers`);
    const items = Array.isArray(result) ? result : result.items ?? [];
    return items.map(normalizeAnswer);
  },
  answer: async (id: string) => normalizeAnswer(await request<unknown>(`/answers/${id}`)),
  saveReview: async (id: string, grading: Grading) => normalizeAnswer(await request<unknown>(`/answers/${id}/review`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      criteria_results: grading.criteria_results.map((criterion) => ({
        criterion_id: criterion.criterion_id,
        status: criterion.status,
        points_awarded: criterion.teacher_points ?? criterion.suggested_points,
        comment: criterion.explanation,
        evidence_from_solution: criterion.evidence_from_solution,
      })),
      transcription: grading.transcribed_latex,
      teacher_comment: grading.teacher_comment ?? "",
    }),
  })),
  approve: async (id: string) => normalizeAnswer(await request<unknown>(`/answers/${id}/approve`, { method: "POST" })),
  reopen: async (id: string) => normalizeAnswer(await request<unknown>(`/answers/${id}/reopen`, { method: "POST" })),
  retry: async (answerId: string) => normalizeAnswer(await request<unknown>(`/answers/${answerId}/retry`, { method: "POST" })),
  retryCrop: async (answerId: string, pageIndex: number, region: Region) => {
    const data = new FormData();
    data.append("page_index", String(pageIndex));
    data.append("region_json", JSON.stringify(region));
    return normalizeAnswer(await request<unknown>(`/answers/${answerId}/retry-crop`, { method: "POST", body: data }));
  },
  exportUrl: (id: string) => `${API_URL}/assignments/${id}/export`,
};
