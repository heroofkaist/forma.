"use client";
import type { CriterionView, EditorValue, ReviewEditor } from "../lib/review-workspace";
import { RubricCriterionCard } from "./review/criterion-card";

/** A single rubric UI for all supported subjects; edits stay in the workspace controller. */
export function RubricReviewPanel({ criteria, editor, expanded, onExpand, onChange, onPage, busy, dirtyKeys }: { criteria: CriterionView[]; editor: ReviewEditor; expanded: string | null; onExpand: (key: string | null) => void; onChange: (key: string, value: Partial<EditorValue>) => void; onPage: (page: number) => void; busy: boolean; dirtyKeys: Set<string> }) {
  return <div className="rw-criteria">{criteria.map((criterion, index) => <RubricCriterionCard key={criterion.key} criterion={criterion} index={index} value={editor.criteria[criterion.key]} open={expanded === criterion.key} onOpen={() => onExpand(expanded === criterion.key ? null : criterion.key)} onChange={value => onChange(criterion.key, value)} onPage={onPage} manual={editor.mode === "manual"} busy={busy} dirty={dirtyKeys.has(criterion.key)}/>)}{!criteria.length && <p className="rw-empty">У задания пока нет критериев. Уточните рубрику перед оцениванием.</p>}</div>;
}
