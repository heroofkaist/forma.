import type { Evidence } from "./review-workspace";
export type TeachingInsight = {
  category: string; tag: string; confirmed_concerns: number; reviewed_submissions: number;
  evidence: {submission_id: string; assignment_id: string; criterion_id: string; decision_id: string; interpretation_id: string; source: Evidence[]}[];
};
export type TeachingInsightsResponse = {items: TeachingInsight[]; denominator: string};
export type InsightsState = {status: "idle" | "loading" | "error" | "loaded"; data: TeachingInsightsResponse | null};
export async function loadTeachingInsights(load: () => Promise<TeachingInsightsResponse>, update: (value: InsightsState) => void) {
  update({status: "loading", data: null});
  try {
    const data = await load();
    if (!Array.isArray(data.items) || data.items.some(i => !Number.isInteger(i.reviewed_submissions) || i.reviewed_submissions < 1 ||
      !Number.isInteger(i.confirmed_concerns) || i.confirmed_concerns < 0 || i.confirmed_concerns > i.reviewed_submissions || !Array.isArray(i.evidence))) throw new Error("Invalid insights");
    update({status: "loaded", data});
  } catch { update({status: "error", data: null}); }
}
