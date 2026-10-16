# File comparison and advisory Qwen profiles

Assignment rows expose separate file-similarity and AI-detector columns. Missing,
failed, stale and unsupported analyses are never displayed as a successful zero.
The AI-detector column is an experimental qualitative style review by the existing
Qwen model, not a calibrated authorship classifier. It returns no authorship
probability, never updates grades, and is not applicable to problem sets/code.
Every displayed model observation must quote an exact supplied source passage and
include a plausible alternative explanation. Teachers see the limitation beside
the results and inside the report.

Local comparison reads each original and validates its content hash. It compares
all extracted text (up to the ingestion limit of 500,000 characters), formula
strings, abstracted code and all eligible PDF pages or embedded Office images.
Visual matching aggregates across both files instead of reporting only the most
similar page. Byte-identical meaningful files are reported explicitly. The overall
index is the strongest applicable text/code/visual signal, not a plagiarism
percentage or an average of unrelated measurements. Qwen concept similarity is a
separate advisory channel, with quotes from both originals. DOCX/PPTX page layouts
are not rendered; scans without embedded text are compared visually and receive no
text-authorship claim. Reformatting and rotation remain limitations.

The archive can compare 2–10 selected files of one course and offers a view of both
originals. Each source is independently authorized; same-author pairs are skipped.
Results are immutable, cached, bound to source hashes and marked stale after a
source or profile changes. GET requests never run paid inference.

Qwen jobs reuse `document_processing_jobs` and the existing provider adapter,
reservations, dedicated key cap, concurrency limit and unknown-billing holds.
Optional `FORMA_INTEGRITY_PROVIDER` selects `openrouter` or `ollama`; otherwise the
existing assessment/AI provider configuration is used. No model or endpoint changes
are made. The hard caps stay $4/month and $0.02/job. Requests over 48,000 UTF-8 text
bytes decline the AI stage before any paid call; local file comparison remains
available. Successful chunks are checkpointed, so resuming a paused job reuses them.
No paid fallback or automatic inference on file views is introduced.

Deploy backend migration `014_document_integrity_profiles` and updated backend
routes before the frontend. The migration is additive. Existing storage and
provider settings are reused; model outputs and student sources stay in private
course storage. Run the synthetic frontend/backend tests without provider keys;
a real paid smoke run should be limited to one explicitly requested document.

References: [GPT detectors and non-native writers](https://arxiv.org/abs/2304.02819)
and [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs).
