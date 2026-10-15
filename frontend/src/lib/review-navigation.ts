export function reviewPath(assignment: { id: string; academic_assignment_id?: string | null }) {
  return assignment.academic_assignment_id
    ? `/teacher/assignments/${assignment.academic_assignment_id}/submissions`
    : `/assignments/${assignment.id}/review`;
}
