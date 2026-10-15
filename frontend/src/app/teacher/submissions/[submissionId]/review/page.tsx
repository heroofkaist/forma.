"use client";
import { useParams } from "next/navigation";
import { AppShell } from "../../../../../components/app-shell";
import { TeacherReviewWorkspace } from "../../../../../components/review/teacher-review-workspace";
export default function DocumentReviewPage() {
  const { submissionId } = useParams<{ submissionId: string }>();
  return <AppShell workspaceClassName="workspace-review"><TeacherReviewWorkspace key={submissionId} submissionId={submissionId}/></AppShell>;
}
