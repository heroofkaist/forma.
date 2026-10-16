# Assignment workspace and local comparison

Implemented locally on 2026-10-16. The course assignment title and its main action now open the assignment workspace, using the existing submissions route. The approved color/typography system is retained. No production data, paid inference, grade publication or deployment is involved.

## Teacher workflow

Course → assignment → student work. The assignment contains active enrollment plus former students who have saved attempts, names, actual Forma account IDs, latest files, immutable attempt history, human review/grade state, saved text-report state, original download and direct document/criteria links. Students without a submission remain visible. Search covers name, ID and filenames; filters separate missing, awaiting review and reviewed work. Published zero scores remain visible and AI processing cannot override a human result.

The existing text/archive percentage retains its established receipt/evidence validation. Missing, failed, insufficient, no-source and incomplete states never display as a successful 0%. The report endpoint and assignment register now share the same summary validation. A student ID is the actual account identifier; no institutional student number is invented. The original and assessment links select the appropriate mobile tab. The register and pair comparisons become labelled cards at narrower widths.

## Explicit local analysis

**Сравнить работы** runs a separate bounded process over the latest attempt of each distinct author in this assignment. Opening the page only reads saved receipts. Inputs and the algorithm version are fingerprinted; repeat requests for unchanged inputs reuse the immutable receipt. New attempts, changed instructions, file identities/hashes or extracted structures mark the saved result stale. A source change during computation rejects the save. Failures do not create a successful zero or overwrite an earlier receipt. Ordinary grade and AI budget tables are not written.

Signals are independent and are shown as coefficients from 0–100, never a combined probability of plagiarism:

- Text: sparse word/unigram/bigram TF-IDF cosine similarity. This can retain similarity when word order changes. It is lexical, not a neural semantic embedding, translation detector or synonym model. Features occurring in the assignment instructions and teacher-supplied common context are excluded; the exact saved context is inspectable.
- Formula notation: vectors of normalized equation-like lines, preserving variable and numeric content. Whitespace normalization is supported; algebraic equivalence, derivation correctness and handwritten recognition are not established.
- Code: normalized five-token fragments with abstracted identifiers/literals; Python adds AST-node fragments. Source is parsed as data and never executed. This is structural resemblance, not proof that two programs implement the same algorithm.
- Visuals: cosine similarity of normalized ink thumbnails of PDF pages, or embedded PNG/JPEG images in DOCX/PPTX. Uniform/blank pages do not get a score. Strong page/image pairs include private original links or embedded asset references. Common layouts/templates can resemble each other. Low resolution, crops, rotation, handwriting changes, small diagrams and missing text remain material limitations; this is not a validated general image-plagiarism detector.

The vector normalization follows standard [TF-IDF/cosine feature extraction](https://github.com/scikit-learn/scikit-learn/blob/main/doc/modules/feature_extraction.rst); the implementation uses Python's standard library and existing dependencies, without installing scikit-learn. PDF visual extraction uses existing [PyMuPDF page rasterization](https://pymupdf.readthedocs.io/en/latest/page.html#Page.get_pixmap), so vector PDF drawings can also enter the page image.

Limits: 2–40 submitted authors, 60 MB of originals combined, 30 MB per file, at most 50 pages in one PDF and 200 pages/embedded images combined. Text vectors use the first 50,000 characters per work; truncation is disclosed in the receipt/UI. Feature vocabularies, AST/token counts, image pixels, archive entries, output size and worker CPU/wall time are bounded. The process has a 30-second wall timeout; Linux adds a 768 MB address-space cap and the worker has a 25-second CPU cap. Limit failures are explicit. This version does not automatically batch larger cohorts or compare the new signals against other assignments, the public web or external databases. The older text/archive report retains its own documented course/family scope.

No broad quality benchmark or educational accuracy claim was made. Synthetic positive/negative controls demonstrate implementation behavior, not real-course detection sensitivity/specificity. Teacher review of originals remains necessary.

## Integration and rollback

- `backend/document_review.py`, `backend/similarity_status.py`, `backend/academic_api.py`: authorized roster/attempt metadata and shared legacy receipt validation.
- `backend/assignment_comparison.py`, `backend/services/similarity_vectors.py`, `backend/comparison_models.py`: explicit local comparison, pure bounded worker and immutable receipts.
- `backend/migrations/__init__.py`, `backend/persistence.py`, `backend/main.py`, `backend/permissions.py`: additive migration **013_local_comparison**, table `assignment_comparisons`, router and concrete course authorization.
- `frontend/src/components/assignment/`, `frontend/src/lib/assignment-workspace.ts`: assignment register, comparison controls, status handling, filtering and history.
- Teacher assignment/submission routes, review overview/workspace, `identity.css` and `presentation.ts`: entry points, IDs, responsive layout and translated errors.
- `backend/tests/test_assignment_workspace.py`, `frontend/tests/assignment-workspace.test.cjs`: focused synthetic regressions.

Backend before frontend on any later approved rollout. No new environment variables or dependencies. Back up the database first; startup applies the additive migration. Rollback: frontend first, then backend; retain `assignment_comparisons` and its immutable receipts. No existing grade, rubric, publication or budget record is migrated.

## Verification

Checks: **235 backend tests passed, 1 skipped**, including tests against a disposable loopback-only PostgreSQL instance. The skip is the explicitly gated paid Gemini test. There were 21 existing dependency/lifecycle deprecation warnings. **68 frontend tests passed**; TypeScript checking and `git diff --check` passed. The final Cloudflare OpenNext rebuild after responsive/copy changes also passed.

The backend tests include a real local worker subprocess, reordered vocabulary, renamed code, normalized formula strings, identical raster-only scanned pages, blank-page guards, context exclusion, no code execution, resource/timeout failure, scoped roster access, immutable attempt grouping, cache reuse, stale receipts and no grade/job/AI-charge writes. Existing receipt-state and publication regressions pass. This is not a real-course accuracy or load benchmark, and does not certify every file parser input.

Chrome inspection covered the authenticated assignment register, student IDs, current human zero/score, missing reports and the loaded saved comparison on a two-student synthetic fixture. The UI POST and metadata reload succeeded against the isolated local backend; no paid request occurred. A desktop capture was inspected and the narrow-layout labels appeared in the accessibility tree. The final 390-pixel frame returned blank captures from the computer-use surface; a complete mobile visual/interaction and cross-browser pass remains unverified. The server/proxy returned successful local responses for that frame.

The temporary preview backend/frontend, local PostgreSQL instance and task-created browser tab were stopped/closed after checks. User services and unrelated tabs were left intact. Commands:

```sh
# Only a disposable local PostgreSQL server/schema, never production.
FORMA_TEST_POSTGRESQL_URL=postgresql://127.0.0.1:55473/postgres PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q --disable-warnings -rs
npm --prefix frontend test
frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json
# From frontend: builds without upload/deployment.
npx --no-install opennextjs-cloudflare build
git diff --check
```
