export type CardUse = {card_id: string; evidence: {page_number: number; observation: string}};
export type DecisionCard = {id: string; title: string; kind: 'decision'|'reference'; rule: string; feedback: string; points: number; source_submission_id: string; review_id: string; evidence: CardUse['evidence']; created_by: string; created_at: string};
export type PageMapping = {id: string; question_id: string; pages: number[]; stale: boolean};
export type QuestionQueue = {title: string; questions: {id: string; title: string}[]; items: {id: string; student_name: string; file_name: string; file_type: string; page_count: number; mapping: PageMapping|null; review_status: string}[]};
export function appendCardExplanation(current: string, explanation: string) {
  const next = explanation.trim();
  if (!next || current.trim() === next || current.split(/\n\s*\n/).some(part => part.trim() === next)) return current;
  return [current, next].filter(Boolean).join('\n\n');
}
export function questionReviewUrl(id: string, question: string, pages: number[] = []) {
  const query = new URLSearchParams({question});
  if (pages.length) query.set('page', String(pages[0]));
  return `/teacher/submissions/${encodeURIComponent(id)}/review?${query}`;
}
export function questionMappingUrl(id: string, question: string) {
  return `${questionReviewUrl(id, question)}&tool=pages#rw-question-pages`;
}
export function needsPageMapping(item: QuestionQueue['items'][number]) {
  return item.file_type === 'pdf' && item.page_count > 0 && (!item.mapping?.pages.length || item.mapping.stale);
}
