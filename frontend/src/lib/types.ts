export type Subject = string;
export type ReviewStatus = "pending" | "processing" | "ready_for_review" | "needs_attention" | "failed" | "approved";
export type CriterionStatus = "awarded" | "not_awarded" | "uncertain";

export type Criterion = {
  id: string;
  criterion_id: string;
  description: string;
  maximum_points: number;
};

export type Region = { x1: number; y1: number; x2: number; y2: number };

export type Question = {
  id: string;
  title: string;
  label?: string;
  statement: string;
  reference_solution: string;
  maximum_points: number;
  criteria: Criterion[];
  region?: Region;
};

export type Assignment = {
  id: string;
  title: string;
  subject: Subject;
  status: string;
  questions: Question[];
  created_at?: string;
  submission_count?: number;
  reviewed_count?: number;
  demo_mode?: boolean;
  template_regions?: Array<Region & { question_id?: string; id?: string; title?: string; page_index?: number }>;
};

export type CriterionResult = {
  criterion_id: string;
  status: CriterionStatus;
  suggested_points: number;
  teacher_points?: number | null;
  explanation: string;
  evidence_from_solution: string;
  manually_overridden?: boolean;
};

export type Grading = {
  transcribed_latex: string;
  transcription_notes: string;
  transcription_status: "readable" | "partially_readable" | "unreadable";
  criteria_results: CriterionResult[];
  overall_feedback: string;
  requires_human_attention: boolean;
  attention_reasons: string[];
  uncertainty?: number;
  total_points?: number;
  approved_total?: number | null;
  teacher_comment?: string;
  is_demo_output?: boolean;
};

export type Answer = {
  id: string;
  assignment_id: string;
  question_id: string;
  anonymous_student_id: string;
  status: ReviewStatus;
  crop_url?: string;
  crop_data_url?: string;
  source_page_url?: string;
  page_index?: number;
  page_number?: number;
  error?: string | null;
  grading?: Grading;
  ai_result_json?: Grading;
};
