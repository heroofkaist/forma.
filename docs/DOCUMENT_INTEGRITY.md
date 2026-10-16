# File comparison and local text signals

Assignment rows show file similarity and AI detector separately. The detector now
runs deterministic Python rules locally: no Qwen, external detector, network
request or token charge. Its version is `local-text-signals-v1`. Old Qwen detector
reports become stale; already queued legacy detector jobs also run locally. The
retained `FORMA_INTEGRITY_PROVIDER` setting has no effect.

The local analyzer inspects all extracted text, up to 500,000 UTF-8 bytes and the
worker's 50-page/unit bound. It finds explicit model self-disclosures, chat/citation
markup and duplicate passages of at least 40 words. Every observation contains an
exact source quote, source unit and possible non-AI explanation. It records word
and sentence counts, lexical diversity and sentence-length variation. These style
statistics do **not** trigger an authorship verdict: regular sentences, polished
language and limited vocabulary alone are not evidence of generation.

This is an inspectable signal checker, **not a trained or calibrated authorship
classifier**. It cannot identify all AI writing; quoted examples, templates and
extraction artifacts can trigger observations. There is no authorship percentage.
No findings does not mean human authorship. Prose shorter than 200 words and
problem sets/code are marked insufficient/not applicable unless an explicit
artifact is present. Scans without extracted text are not analyzed. Coverage and
limitations are shown in the report. No detector action changes grades.

GET only reads a saved report. Explicit teacher requests use durable private
`document_processing_jobs` with a `local` provider and zero cost, independent of
paid-provider availability. Local checks do not consume the model-job daily
allowance. No new migration, model download or secret is required.

File comparison still validates each original's content hash and compares all
extracted text, formula strings, normalized code and eligible PDF pages or embedded
Office images. The overall index is the strongest text/code/visual signal; it is
not a plagiarism probability. DOCX/PPTX layouts are not rendered. Historical saved
Qwen concept channels remain labeled as such; new local detector reports do not
create or invent semantic profiles. Reformatting, OCR gaps and rotation remain
limitations. The archive compares authorized files across the shared course
archive; same-author pairs are skipped. Results are cached, immutable and marked
stale when sources change.

The limitations are consistent with research on [detector bias for non-native
writers](https://arxiv.org/abs/2304.02819) and [detector robustness under editing and
paraphrasing](https://aclanthology.org/2024.acl-long.160/). Synthetic tests verify
local-only execution, exact evidence, coverage, missing results, permissions,
idempotency, zero charges and unchanged grades. They do not establish detection
accuracy on a labeled academic corpus.
