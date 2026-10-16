"use client";
import type { CriterionView, EditorValue, ReviewEditor, SavedReviewState } from "../lib/review-workspace";
import { RubricCriterionCard } from "./review/criterion-card";

/** A single rubric UI for all supported subjects; edits stay in the workspace controller. */
export function RubricReviewPanel({ criteria, editor, onChange, onPage, busy, dirtyKeys, savedState }: { criteria: CriterionView[]; editor: ReviewEditor; onChange: (key: string, value: Partial<EditorValue>) => void; onPage: (page: number) => void; busy: boolean; savedState: SavedReviewState; dirtyKeys: Set<string> }) {
  return <div className="rw-criteria">{criteria.map((criterion, index) => <RubricCriterionCard key={criterion.key} criterion={criterion} index={index} value={editor.criteria[criterion.key]} onChange={value => onChange(criterion.key, value)} onPage={onPage} manual={editor.mode === "manual"} busy={busy} dirty={dirtyKeys.has(criterion.key)} savedState={savedState}/>)}{!criteria.length && <p className="rw-empty">У задания пока нет критериев. Уточните рубрику перед оцениванием.</p>}</div>;
}
