import { notFound } from "next/navigation";
import { ReviewViewportPreview } from "../../../../components/review/review-viewport-preview";
export default async function ReviewPreview({ params }: { params: Promise<{ submissionId: string }> }) {
  if (process.env.NODE_ENV !== "development") notFound();
  const { submissionId } = await params;
  return <ReviewViewportPreview submissionId={submissionId}/>;
}
