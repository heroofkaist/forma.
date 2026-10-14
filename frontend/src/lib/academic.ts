import { API_URL, authenticatedFetch } from "./api";

export type Offering = {
  id: string;
  course_id: string;
  code: string;
  name: string;
  instructor?: string;
  instructor_name?: string;
  academic_year: string;
  term: string;
  section?: string;
  status: string;
  pending_assignments?: number;
  assignments?: AcademicAssignment[];
  class_code?: string;
  enrollment_count?: number;
  assignment_count?: number;
  course?: Course;
  course_code?: string;
  course_name?: string;
  reused_from?: string | null;
};

export type Course = {
  id: string;
  code: string;
  name: string;
  instructor?: string;
  department?: string;
  offerings: Offering[];
};

export type AcademicAssignment = {
  id: string;
  offering_id: string;
  assignment_template_id?: string | null;
  family_id?: string;
  assignment_family_id?: string | null;
  title: string;
  assignment_type: "problem_set" | "essay" | "lab_report" | "presentation" | "research_report" | "programming" | "general";
  description: string;
  available_at?: string | null;
  due_at?: string | null;
  maximum_score: number;
  allow_resubmission: boolean;
  originality_enabled: boolean;
  originality_scope: string;
  status: string;
  submission_status?: string;
  grade?: number | null;
  published_at?: string | null;
  questions?: Array<Record<string, unknown>>;
  original_assignment_id?: string | null;
  reused_from?: string | null;
  legacy_assignment_id?: string | null;
  submission_count?: number;
  latest_submission?: Record<string, unknown> | null;
};

export type SimilarityMatch = {
  id: string;
  source_submission_id?: string;
  source_title?: string;
  source_course?: string;
  source_assignment?: string;
  source_term?: string;
  matched_excerpt: string;
  current_text_start: number;
  current_text_end: number;
  source_text_start: number;
  source_text_end: number;
  similarity_method: string;
  source_excerpt?: string;
  report_id?: string;
  review_status?: string;
};

export type SimilarityReport = {
  id: string;
  submission_id: string;
  analysis_status: string;
  matched_text_ratio: number;
  analysis_scope: string;
  created_at?: string;
  extracted_text?: string;
  eligible_token_count?: number;
  excluded_token_count?: number;
  matches: SimilarityMatch[];
  review_status?: string;
  teacher_notes?: string;
  course?: string;
  assignment?: string;
  student_id?: string;
  academic_year?: string;
  document_title?: string;
  document_type?: string;
  exclusion_rules?: string[];
};

export type ArchiveSubmission = {
  submission_id: string;
  assignment_id: string;
  assignment_title: string;
  academic_year: string;
  term: string;
  student_id: string;
  file_name: string;
  file_type: string;
  submitted_at?: string | null;
  extracted_text: string;
  course_name?: string;
  course_code?: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authenticatedFetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = typeof body?.detail === "string" ? body.detail : `Request failed (${response.status}).`;
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

function unwrap<T>(value: { items?: T[] } | T[]): T[] {
  return Array.isArray(value) ? value : value.items ?? [];
}

function normalizeAssignment(raw: Record<string, unknown>): AcademicAssignment {
  const reusedFrom = typeof raw.reused_from === "string" ? raw.reused_from : null;
  return {
    ...raw,
    id: String(raw.id),
    offering_id: String(raw.offering_id),
    family_id: String(raw.family_id ?? ""),
    title: String(raw.title ?? "Задание"),
    assignment_type: String(raw.assignment_type ?? "general") as AcademicAssignment["assignment_type"],
    description: String(raw.description ?? ""),
    maximum_score: Number(raw.maximum_score ?? 0),
    allow_resubmission: Boolean(raw.allow_resubmission),
    originality_enabled: Boolean(raw.originality_enabled),
    originality_scope: String(raw.originality_scope ?? "family_then_course"),
    status: String(raw.status ?? "published"),
    reused_from: reusedFrom,
    original_assignment_id: reusedFrom,
    legacy_assignment_id: typeof raw.legacy_assignment_id === "string" ? raw.legacy_assignment_id : null,
    submission_count: Number(raw.submission_count ?? 0),
  };
}

function normalizeOffering(raw: Record<string, unknown>, course?: Course): Offering {
  const embedded = raw.course && typeof raw.course === "object" ? raw.course as Record<string, unknown> : {};
  const owner = course ?? {
    id: String(embedded.id ?? raw.course_id ?? ""),
    code: String(embedded.code ?? raw.course_code ?? ""),
    name: String(embedded.name ?? raw.course_name ?? raw.name ?? ""),
    instructor: String(embedded.instructor ?? raw.instructor ?? ""),
    department: String(embedded.department ?? ""),
    offerings: [],
  };
  return {
    id: String(raw.id),
    course_id: String(raw.course_id ?? owner.id),
    course_code: owner.code,
    course_name: owner.name,
    code: owner.code,
    name: owner.name,
    instructor: String(raw.instructor ?? owner.instructor ?? ""),
    instructor_name: String(raw.instructor ?? owner.instructor ?? ""),
    academic_year: String(raw.academic_year ?? ""),
    term: String(raw.term ?? ""),
    section: String(raw.section ?? ""),
    status: String(raw.status ?? ""),
    class_code: typeof raw.class_code === "string" ? raw.class_code : undefined,
    pending_assignments: Number(raw.pending_assignments ?? 0),
    enrollment_count: typeof raw.enrollment_count === "number" ? raw.enrollment_count : undefined,
    assignment_count: Array.isArray(raw.assignments) ? raw.assignments.length : undefined,
    assignments: Array.isArray(raw.assignments) ? raw.assignments.map((item) => normalizeAssignment(item as Record<string, unknown>)) : undefined,
    course: owner,
  };
}

function normalizeReport(raw: Record<string, unknown>) : SimilarityReport {
  const evidence = Array.isArray(raw.evidence) ? raw.evidence as Record<string, unknown>[] : [];
  const reportId = String(raw.id ?? "");
  const matches: SimilarityMatch[] = evidence.map((item, index) => {
    const sourceOffsets = item.source_offsets as { start?: number; end?: number } | undefined;
    const candidateOffsets = item.candidate_offsets as { start?: number; end?: number } | undefined;
    return {
      id: `${reportId}-${index}`,
      report_id: reportId,
      source_submission_id: String(raw.candidate_submission_id ?? ""),
      source_title: String(raw.source_title ?? "Архивная работа"),
      source_course: String(raw.source_course ?? ""),
      source_assignment: String(raw.source_assignment ?? ""),
      source_term: String(raw.source_term ?? ""),
      matched_excerpt: String(item.candidate_excerpt ?? ""),
      source_excerpt: String(item.source_excerpt ?? ""),
      review_status: String(raw.review_status ?? "unreviewed"),
      current_text_start: Number(sourceOffsets?.start ?? 0),
      current_text_end: Number(sourceOffsets?.end ?? 0),
      source_text_start: Number(candidateOffsets?.start ?? 0),
      source_text_end: Number(candidateOffsets?.end ?? 0),
      similarity_method: "normalized-token-sequence",
    };
  });
  return {
    ...raw,
    id: reportId,
    submission_id: String(raw.submission_id ?? ""),
    analysis_status: "ready",
    matched_text_ratio: Number(raw.match_ratio ?? 0),
    analysis_scope: String(raw.match_scope ?? ""),
    created_at: typeof raw.created_at === "string" ? raw.created_at : undefined,
    extracted_text: typeof raw.extracted_text === "string" ? raw.extracted_text : undefined,
    eligible_token_count: Number(raw.eligible_token_count ?? 0),
    matches,
    review_status: String(raw.review_status ?? "unreviewed"),
    teacher_notes: String(raw.teacher_notes ?? ""),
    course: String(raw.course_name ?? raw.course_code ?? ""),
    assignment: String(raw.assignment_title ?? ""),
    student_id: String(raw.student_id ?? ""),
    academic_year: String(raw.academic_year ?? ""),
    document_title: String(raw.document_title ?? raw.file_name ?? ""),
  };
}

function json(body: unknown): RequestInit {
  return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export const academicApi = {
  courses: async (role: "student" | "teacher") =>
    unwrap(await request<{ items?: Course[] } | Course[]>(`/academic/courses?role=${role}`)),
  offerings: async () => {
    const courses = await academicApi.courses("teacher");
    const offerings = courses.flatMap((course) => course.offerings.map((offering) => normalizeOffering(offering as unknown as Record<string, unknown>, course)));
    return Promise.all(offerings.map(async (offering) => {
      const assignments = await academicApi.offering(offering.id);
      return { ...offering, ...assignments, course_code: offering.course_code, course_name: offering.course_name, code: offering.code, name: offering.name, assignments: assignments.assignments };
    }));
  },
  offering: async (id: string, role: "student" | "teacher" = "teacher") => {
    const raw = await request<Record<string, unknown>>(`/academic/offerings/${id}?role=${role}`);
    const normalized = normalizeOffering(raw);
    return { ...normalized, assignments: Array.isArray(raw.assignments) ? raw.assignments.map((item) => normalizeAssignment(item as Record<string, unknown>)) : [] };
  },
  enroll: (classCode: string) => request<Offering>("/academic/enroll", json({ class_code: classCode })),
  studentAssignments: async (): Promise<AcademicAssignment[]> => {
    const items = unwrap<Record<string, unknown>>(await request<{ items?: Record<string, unknown>[] } | Record<string, unknown>[]>("/academic/student/assignments"));
    return items.map((item) => {
      const deadline = typeof item.due_at === "string" ? new Date(item.due_at).getTime() : null;
      const hasSubmission = Boolean(item.submission);
      const submissionStatus = item.published_grade ? "graded" : hasSubmission ? "submitted" : deadline !== null && deadline < Date.now() ? "overdue" : "not_started";
      return normalizeAssignment({
        ...item,
        status: "published",
        latest_submission: item.submission,
        submission_status: submissionStatus,
        grade: (item.published_grade as Record<string, unknown> | null)?.points,
        published_at: (item.published_grade as Record<string, unknown> | null)?.published_at,
      });
    });
  },
  assignment: async (id: string) => {
    const items = await academicApi.studentAssignments();
    const assignment = items.find((item) => item.id === id);
    if (!assignment) throw new Error("Задание не найдено среди курсов студента.");
    return assignment;
  },
  submit: (assignmentId: string, file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<Record<string, unknown>>(`/academic/assignments/${assignmentId}/submissions`, { method: "POST", body: data });
  },
  studentGrades: async () =>
    unwrap(await request<{ items?: Record<string, unknown>[] } | Record<string, unknown>[]>("/academic/student/grades")),
  createOffering: (payload: Record<string, unknown>) => request<Offering>("/academic/offerings", json(payload)),
  createAssignment: (payload: Record<string, unknown>) => request<AcademicAssignment>("/academic/assignments", json(payload)),
  reuseAssignment: (assignmentId: string, payload: Record<string, unknown>) =>
    request<AcademicAssignment>(`/academic/assignments/${assignmentId}/reuse`, json(payload)),
  originalityQueue: async () =>
    unwrap(await request<{ items?: Record<string, unknown>[] } | Record<string, unknown>[]>("/academic/teacher/originality")).map(normalizeReport),
  originalityReport: async (submissionId: string) => {
    const response = await request<{ submission_id: string; items: Record<string, unknown>[] }>(`/academic/submissions/${submissionId}/originality`);
    const reports = response.items.map(normalizeReport);
    if (!reports.length) throw new Error("Для этой работы нет отчёта о совпадениях.");
    const [primary] = reports;
    return { ...primary, matches: reports.flatMap((report) => report.matches) };
  },
  reviewOriginality: (reportId: string, payload: { review_status: string; teacher_notes: string }) =>
    request<SimilarityReport>(`/academic/reports/${reportId}/review`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
  archive: async (query = "") =>
    {
      const offerings = await academicApi.offerings();
      const assignments = offerings.flatMap((offering) => (offering.assignments ?? []).map((assignment) => ({ offering, assignment })));
      const pages = await Promise.all(assignments.map(async ({ offering, assignment }) =>
        unwrap(await request<{ items?: ArchiveSubmission[] } | ArchiveSubmission[]>(`/academic/teacher/assignments/${assignment.id}/archive`))
          .map((item) => ({ ...item, course_name: offering.course_name, course_code: offering.course_code })),
      ));
      const normalizedQuery = query.trim().toLocaleLowerCase("ru-RU");
      const unique = new Map(pages.flat().map((item) => [item.submission_id, item]));
      return [...unique.values()].filter((item) => !normalizedQuery || `${item.course_name} ${item.course_code} ${item.assignment_title} ${item.academic_year} ${item.term} ${item.file_name} ${item.file_type} ${item.extracted_text}`.toLocaleLowerCase("ru-RU").includes(normalizedQuery));
    },
  publish: (assignmentId: string) => request<Record<string, unknown>>(`/academic/assignments/${assignmentId}/publish`, { method: "POST" }),
};
