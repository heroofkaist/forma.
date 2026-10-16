export type PublishedGrade = {
  id: string;
  review_id?:string;
  assignment_id: string;
  assignment_title: string;
  submission_id: string;
  points: number;
  maximum_score: number;
  published_at: string | null;
  feedback: string;
  criteria: Array<{
    question_id: string;
    criterion_id: string;
    description?: string;
    maximum_points?: number | null;
    points: number;
    comment: string;
  }>;
};

export function criterionTitle(criterion: PublishedGrade["criteria"][number], index: number) {
  const title = criterion.description?.trim();
  return title && title !== criterion.criterion_id ? title : `Критерий ${index + 1}`;
}
