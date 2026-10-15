/** Prohibited controls are removed from the DOM, including keyboard/file-drop targets. */
export function SubmissionGate({ reason, children }: { reason: string; children: React.ReactNode }) {
  return reason ? <div className="closed-notice" role="status">{reason}</div> : <>{children}</>;
}
