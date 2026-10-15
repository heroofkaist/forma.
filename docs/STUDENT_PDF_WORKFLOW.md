# Student-first PDF submission workflow

## Inspection and changes

Already connected before this change: approved institutional teachers can create academic assignments with no template/questions/reference PDF; students join by course code, open assignments and upload multi-page PDFs; originals use private R2 helpers; upload persists a ProcessingJob in the submission transaction; the leased PostgreSQL worker invokes Phase 3 Gemini understanding; authorized teacher review loads the original PDF and immutable analysis/correction versions. These components were reused.

Disconnected UI: `/assignments/new` still created a legacy-only assignment and forced a template redirect. It now selects an authorized course offering, creates an academic problem-set assignment and opens its submissions page. The course-specific assignment editor remains available for types, dates and optional rubric definitions. Neither path requires reference PDFs, crops or annotations. Existing legacy assignments/template routes and data remain intact.

Teacher submission lists now poll the authorized list API and show the latest processing state and safe processing errors separately from grade status. Optional question-sheet upload is collapsed and explicitly labelled optional. Student status polling now exposes safe processing failures and connection failures instead of silently swallowing them. The original upload receipt survives processing failure.

## Product path

1. Approved teacher creates a course and shares its enrollment code.
2. Teacher creates an assignment via `/assignments/new` or the course assignment editor; no template step follows.
3. Verified student enrolls via `/student/join`, opens the course assignment, chooses their own PDF and confirms upload.
4. The original is stored privately, deterministic extraction validates the document, and a durable job is queued. Students can see queued, extraction/interpretation, ready-for-review, confirmed and failed states.
5. Teacher opens Works and review, then Review. Original PDF page navigation/zoom appears alongside extracted sections, formulas/transcription, page associations and qualitative uncertainty. Teachers can correct/split/merge/reassign and confirm structure. Phase 3 confirmation never assigns/publishes grades. Existing explicit manual grading remains separate.

`needs_review` means analysis finished and teacher review is pending; `completed` means the teacher confirmed structure. They are distinct from academic submission/grade statuses. There are no fabricated correctness scores or confidence percentages.

## Changed files

- `backend/document_review.py`: authorized submission listing includes latest job state/error, using one batched job query.
- `frontend/src/app/assignments/new/page.tsx`: course-linked creation with no mandatory template or rubric.
- `frontend/src/app/student/assignments/[assignmentId]/page.tsx`: visible processing/polling errors.
- `frontend/src/app/teacher/assignments/[assignmentId]/submissions/page.tsx`: live processing states, errors and optional task sheet.
- `backend/tests/test_student_pdf_workflow.py`: real PDF upload through job processing, original access, teacher correction, cross-course denials and provider-failure retry.
- `docs/STUDENT_PDF_WORKFLOW.md`: this inspection, verification and rollout record.

## Verification and limits

Verification: backend **70 passed, 3 skipped** (PostgreSQL integration unavailable), with 21 dependency/lifecycle deprecation warnings; frontend **8 passed**; TypeScript checking, Next.js production build and OpenNext Cloudflare bundle passed; `git diff --check` passed.

Automated workflow tests use synthetic three-page PDFs, local private storage and isolated SQLite; the provider is deterministic/mocked. Existing processing tests cover bounded Gemini requests, atomic claims, stale leases and retries. No live Gemini, R2, Neon, SMTP or production checks were run. Browser appearance has not been visually verified. PostgreSQL-specific tests require a separate `FORMA_TEST_POSTGRESQL_URL`; never point it at production.

Existing Phase 3 limits remain: 30 MB/50 pages, bounded visual-page budget (default eight, cap twelve), bounded model inputs/output and retries. Initial validation/text extraction runs during upload; Gemini understanding runs asynchronously. PDF visual interpretation currently renders image-only pages, so diagrams embedded in pages with substantial extracted text may need manual review. Regions are page-level sections, not pixel bounding boxes. Handwriting/formula accuracy requires teacher verification. Without Gemini configuration the system explicitly reports deterministic extraction only. Render Free processes jobs only while awake; leases recover after restart. Model calls are at-least-once across crashes. No new schema migration or infrastructure is introduced by this follow-up.

## Exact deployment procedure — only after approval

1. Review/commit the listed local changes through the normal repository workflow. Back up the existing database and retain private R2 objects. Rehearse on staging first. This follow-up adds no migration; a deployment must already have Phase 3 additive migrations 001–006. Backend startup applies missing reviewed migrations under the existing advisory lock.
2. Preserve current Render auth, institution, SMTP, database, R2 and Gemini settings. Confirm `FORMA_AUTH_REQUIRED=true`, `FORMA_DEMO_MODE=false`, `FORMA_STORAGE_BACKEND=r2`, `FORMA_DOCUMENT_WORKER_ENABLED=true` (default). Keep the existing model setting and exact HTTPS `FRONTEND_ORIGIN`. Do not rotate keys or assign roles automatically.
3. In Render, select the existing `forma-api` service, choose **Manual Deploy → Deploy a specific commit**, and select the reviewed commit. Retain these configured commands:

   ```sh
   pip install -r backend/requirements.txt
   cd backend && uvicorn main:app --host 0.0.0.0 --port "$PORT"
   ```

   Check `/api/health` and startup/migration/worker logs before frontend rollout. Approve intended teacher roles through the existing reviewed operator procedure if not already configured.
4. Preserve the existing Cloudflare Worker `FORMA_BACKEND_URL` binding pointing to that Render HTTPS service. Preserve cookies/origin protection and proxy `redirect: "manual"`. From the reviewed checkout:

   ```sh
   cd frontend
   npm ci
   npm test
   npx tsc --noEmit
   npm run cf:deploy
   ```

   `cf:deploy` builds Next/OpenNext and publishes to the existing Worker using its existing Wrangler configuration/account. Run this publishing command only after deployment approval; no publish was performed during implementation.
5. On staging, use separate verified teacher/student accounts: create template-free assignment, enroll student, upload synthetic three-page PDF, observe queued/processing/ready, download original, correct and confirm structure. Verify unrelated student/teacher access is denied and no grade was created. Exercise safe provider failure/retry and backend restart with a queued job. Check a legacy template assignment still opens unchanged. Repeat a small synthetic smoke check on production after the approved rollout.
6. Roll back frontend/backend application revisions together if needed. Retain all submissions, originals, jobs and Phase 3 additive tables; do not drop data. No credentials, production data, deployment or paid services were changed by this local work.
