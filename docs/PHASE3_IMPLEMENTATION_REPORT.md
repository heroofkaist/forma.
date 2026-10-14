# Phase 3 implementation and role architecture

## 1. Roles

Public registration now creates an explicit `student` role. Database sessions load the current role on every request; a login form, profile JSON, frontend state or course code cannot promote an account. Teacher and student permissions are exclusive. `teacher`, `school_admin` and `platform_admin` require administrative approval. The transitional `migration_pending` status is limited to accounts that already own historical courses/legacy assignments; it preserves those owned resources without allowing unrestricted course creation or student enrollment. Accounts, verification state and sessions are not deleted or mass-promoted.

Frontend routing uses authenticated role rather than the requested login experience. Student pages, teacher pages and institution administration have distinct navigation. Settings remain shared. There is no role-switch control. Backend authorization remains authoritative; frontend route guards are usability controls, not the security boundary.

## 2. Institutional authorization

Institutions have approved teacher/admin memberships and explicit course associations. A teacher creates courses only with an active teaching membership in the selected institution, and manages owned courses. A school admin manages courses and teachers only where the actual institution membership grants admin rights. Being a school admin in institution A does not expand teacher-only membership in B. Suspended teacher memberships lose course access immediately on subsequent requests. Legacy environment teachers retain their existing unclaimed historical scope and cannot manage new institutional courses.

Administrators can create institutions (platform admin), rename authorized institutions, list/invite teachers, and suspend/restore teacher memberships. Teacher invitation mail reuses the existing encrypted durable SMTP outbox and Brevo configuration. Recipients must register and verify their account; acceptance is authenticated, account-bound, single-use, expiring and explicitly confirms role transition. Active student enrollments block acceptance pending operator review. The inviter's current authority is checked again at acceptance. No institutional privileges are inferred from domains or the first signup.

## 3. Additive migrations

- `005_institution_roles`: `account_roles`, `institutions`, `institution_memberships`, `course_institutions`, `teacher_invitations`, `audit_events`.
- `006_document_understanding_jobs`: `document_processing_jobs`, `document_interpretations`, `interpretation_corrections`, `document_interpretation_cache`, `assignment_briefs`.

These migrations create only new named tables with foreign keys, under the existing transactional PostgreSQL advisory lock. Historical ownership, enrollments, submissions, grade/review records and accounts are preserved. No public account is automatically assigned elevated rights. Existing initialization excludes these new tables and delegates their creation to the explicit migration ledger. Repeated initialization/migration and preserved records are tested.

## 4. Exact operator bootstrap

Do not execute these commands against production until the account, memberships, backup and institution plan are reviewed. This implementation has not run a production bootstrap or changed production roles.

1. Back up the database; deploy/rehearse the additive migrations in a safe staging database first. Retain current auth/SMTP/R2 secrets and legacy operator login.
2. Identify the exact **verified active account UUID** through a private operator database session. Do not select by an ambiguous display name or automatically by email domain.
3. From `backend`, with the intended private database configuration, execute:

   ```sh
   .venv/bin/python scripts/approve_account_role.py ACCOUNT_UUID platform_admin --confirm 'APPROVE:ACCOUNT_UUID:platform_admin'
   ```

4. The trusted operator signs in and creates institutions through `/admin/institutions`. The CLI can approve a reviewed school administrator:

   ```sh
   .venv/bin/python scripts/approve_account_role.py ACCOUNT_UUID school_admin --institution INSTITUTION_UUID --confirm 'APPROVE:ACCOUNT_UUID:school_admin'
   ```

5. Approve an existing verified course owner with `teacher` in the same command pattern. Add `--claim-course COURSE_UUID` only for that account's own existing course. The command refuses ownership changes and transfers from another institution. It does not rewrite ownership or enrollments by default.
6. Active student enrollments cause refusal. After explicit membership review, `--review-enrollments` suspends those enrollments and records each change while retaining academic history. This is a deliberate role transition, not a casual user switch.

The CLI is not exposed by an API, requires the exact account ID/role confirmation, checks verification/status/institution, emits audit records, avoids secrets and is safe to rerun. Rerunning may add another audit event but does not duplicate memberships or elevate additional accounts. Keep legacy login enabled until trusted operator and affected account/course transitions are validated. Role rollback requires explicit review; do not drop new tables.

## 5. Phase 3 processing

Upload validates and stores originals through existing private R2 helpers. PDF/DOCX/PPTX/source extraction is reused. A durable job is enqueued for authenticated submissions; if the daily budget is exhausted, the receipt remains and the submission reports analysis not scheduled. Teachers can schedule/re-analyze from the review page. Old submissions can be analyzed on request.

PostgreSQL jobs store submission/content/input hashes, immutable assignment-question context, model/prompt version, attempts, stage, timestamps, lease owner/expiry and classified errors. Claims use conditional UPDATE/RETURNING plus a short PostgreSQL advisory transaction lock to enforce the global concurrency limit. SQLite tests use a serialized write lock. Leases expire after five minutes; interrupted jobs recover with bounded attempts. Late workers cannot overwrite a new lease or expired result. Provider/storage transient errors retry with backoff, at most three attempts; invalid evidence fails for teacher review. No grade is assigned by this pipeline.

A small daemon worker runs only while the backend is awake. Sleeping Render Free instances do not process documents. Queued metadata and R2 originals survive restart; the startup worker polls again and stale leases recover. There is no always-on throughput guarantee. Set `FORMA_DOCUMENT_WORKER_ENABLED=false` when using an explicitly configured alternative worker; `document_processing.process_one()` provides a single-work-item entry point. No Redis/Celery/paid service was introduced.

Defaults: 30 MB upload, 50 PDF pages/PPTX slides, 50 processing units/job, eight visual pages (hard cap 12), one global active job (cap two), 60-second Gemini timeout (cap 90), three attempts, 20 newly scheduled jobs per requester/day, three analysis versions/submission/day, 64,000 source-text characters/model request, a 24,000-character assignment-instruction budget, 12,000 output tokens. SDK internal retries are disabled so the durable retry budget is authoritative. Long sources and unprocessed scanned pages are disclosed. Token usage is recorded when Gemini provides it; no invented costs or confidence percentages are shown.

Repeated requests reuse the same job for a submission/context/model/prompt. Validated AI results can be cached for identical content/questions/model within the same course offering; unrelated institutions/offerings never share a cache key. Explicit re-analysis bypasses cache but remains bounded. Remote model calls are at-least-once across a process crash after provider response and before commit; exactly-once billing is not claimed.

## 6. AI capabilities and boundaries

Gemini receives deterministic text and bounded normalized page images from image-only PDFs. It proposes document sections, equations, diagrams/tables, transcriptions, question associations and cross-page continuations. The prompt is versioned `document-understanding-v1`, reuses the configured Gemini model/key, treats every document as untrusted data, forbids grading/invented measurements and requests uncertainty rather than fabricated certainty. Structured responses are locally validated in addition to [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output).

Page numbers must exist; visual evidence may reference only pages actually sent; embedded-text transcriptions must quote actual extracted text; unknown question IDs, duplicated IDs, unsupported associations and model teacher-confirmation claims are rejected. Unreadable content is not treated as an incorrect answer. Images do not have invented boxes: localization is page-level. Visual transcriptions cannot be independently verified from pixels by schema validation and still require teacher confirmation.

Teachers can upload a task sheet from an assignment's submissions screen. Deterministic explicit question headings are proposed, editable and require approval before future interpretation uses them. This does not replace the grading rubric. Image-only teacher task sheets currently require manual question entry; no crop template is needed. Existing assignment instructions/questions work without a task-sheet file.

Essays/lab/research reports retain source sections and can be interpreted by the model. PPTX uses slide text/tables only; it has no slide visual renderer or delivery evaluation. DOCX references are document units, not fabricated physical pages. Programming files remain static and are never executed. AI rubric generation, source-material retrieval and universal AI grading are **not** implemented or claimed in Phase 3. The legacy crop grader remains an optional compatibility tool.

## 7. Correction UI

The existing split review workspace shows the original PDF with page navigation/zoom or extracted text for other formats. A connected analysis panel shows queue status, source units, section transcriptions, readability, proposed questions, associated pages and warnings. Teachers can correct text, reassign questions, mark unreadable/missing content, split at an explicit blank line, merge adjacent same-page sections, logically associate multi-page continuations with a shared question, save correction versions and confirm structure. Re-analysis is bounded.

Original AI output and each correction remain separate database records. Corrections are tenant/course-authorized and validated against the job's question snapshot. Confirmation marks processing completed but never publishes a grade. The existing manual rubric/grading workflow remains explicit. There are no fabricated region highlights. Browser-native PDF zoom support may vary. Pixel-level visual QA has not been completed in this implementation; tests/builds do not substitute for browser appearance review.

## 8. UI bugs fixed

Archive, courses, review, originality, settings and administration use actual route breadcrumbs. Each maps to one primary sidebar key; nested `/teacher` paths no longer select Courses plus Archive/Originality simultaneously. Added a real review queue backed by authorized submissions. Removed authenticated and demo role-switch links, obsolete local-prototype/closed-demo archive messages, and role-generic registration wording. Protected children remain hidden while identity loads or a forbidden route redirects. Course creation/institution errors are visible, and processing pending/failed/missing states do not display fake success.

## 9. Verification

Baseline rerun: backend 50 passed, two PostgreSQL skips; frontend proxy 4 passed/1 failed because it still expected `redirect: error`. Updated that obsolete assertion to the production-required `manual`; no Worker fetch uses `redirect: error`.

Final checks: backend **68 passed, 3 skipped** (PostgreSQL-only), with 21 existing dependency/lifecycle deprecation warnings; frontend **8 passed**; TypeScript checking, Next.js production build and OpenNext Cloudflare bundle passed. `git diff --check` passed. Synthetic fixtures exercise strict roles, invitation scope/expiry/replay, explicit bootstrap, membership revocation, legacy-owner transition, two-institution isolation, durable concurrent claims, stale leases, backoff/exhaustion, digital and image-only PDFs, multi-page solutions, missing/unreadable answers, schema grounding, mocked visual Gemini requests, same-offering caching, bounded re-analysis, task-sheet approval, corrections and version retention. Existing DOCX/PPTX/tables/malformed/oversize/grade/session regressions are retained. Frontend tests cover role navigation/breadcrumb keys and the same-origin cookie/CSRF/manual-redirect proxy.

## 10. Limitations and skipped integration checks

`FORMA_TEST_POSTGRESQL_URL` is not configured. A local PostgreSQL server was not available, and Docker's daemon was not running. The three PostgreSQL-specific tests are skipped; production Neon was not used for tests. PostgreSQL claim/advisory-lock behavior still requires staging validation, particularly concurrent workers and migration rollback rehearsal.

No `FORMA_TEST_GEMINI_API_KEY` is configured for a safe integration environment. Gemini is mocked in automated tests; production credentials and real student documents were not used. A configured deployment exercises the real SDK call; handwriting accuracy and selected deployed model compatibility still need a bounded synthetic staging run. If Gemini is unavailable, deterministic extraction is clearly disclosed; no OCR is pretended. Initial normalize/extract still runs in the upload thread pool before durable interpretation. Historical extraction can run in the worker. Cache/retention cleanup and comprehensive cancellation UI are future operations work.

## 11. Before production deployment

Back up and rehearse migrations 005/006. Deploy coordinated backend/frontend versions so the new role values and required institution IDs are understood. Do not rotate secrets, change Brevo settings, reset R2, mass-assign roles or push/deploy automatically. Explicitly approve the intended operator, create institutions and review historical owners/courses. Keep the existing Worker backend binding, HttpOnly cookies and `redirect: manual` proxy. Confirm Render worker settings/budgets and private R2 access; validate queued resume after sleeping/restart. Check a synthetic task sheet, scanned answer, correction and invitation delivery on staging. This implementation has changed local source only.

## 12. Phase 4 next steps

Use immutable confirmed interpretations/question snapshots as assessment input. Add reviewed rubric proposals, permission-scoped reference passage retrieval and validated source citations. AI grading must use approved rubric limits and adequate readable evidence, keep suggestions separate from reviewed/published grades, preserve override history and record usage without invented costs. Complete staging PostgreSQL/Gemini and browser verification before expanding automatic assessment.

## Local files changed

The pre-existing proxy change (`redirect: "manual"` and diagnostics) was preserved and is excluded from this implementation list. No production deployment, push, database operation, SMTP configuration or secret changes were performed.

- `.env.example`
- `README.md`
- `backend/academic_api.py`
- `backend/accounts.py`
- `backend/analysis_api.py`
- `backend/assignment_briefs.py`
- `backend/courses.py`
- `backend/document_processing.py`
- `backend/email_delivery.py`
- `backend/institution_models.py`
- `backend/institutions.py`
- `backend/main.py`
- `backend/migrations/__init__.py`
- `backend/permissions.py`
- `backend/persistence.py`
- `backend/processing_models.py`
- `backend/scripts/approve_account_role.py`
- `backend/services/ai_grader.py`
- `backend/services/document_understanding.py`
- `backend/tests/conftest.py`
- `backend/tests/test_academic_seed.py`
- `backend/tests/test_accounts_courses.py`
- `backend/tests/test_document_processing.py`
- `backend/tests/test_institution_roles.py`
- `backend/tests/test_processing_postgresql.py`
- `docs/ACCOUNT_MIGRATION_AND_DEPLOYMENT.md`
- `docs/PHASE3_IMPLEMENTATION_REPORT.md`
- `docs/PRODUCT_EVOLUTION_PLAN.md`
- `frontend/src/app/admin/institutions/page.tsx`
- `frontend/src/app/login/page.tsx`
- `frontend/src/app/page.tsx`
- `frontend/src/app/student/assignments/[assignmentId]/page.tsx`
- `frontend/src/app/teacher-invitation/page.tsx`
- `frontend/src/app/teacher/archive/page.tsx`
- `frontend/src/app/teacher/assignments/[assignmentId]/submissions/page.tsx`
- `frontend/src/app/teacher/courses/new/page.tsx`
- `frontend/src/app/teacher/page.tsx`
- `frontend/src/app/teacher/review/page.tsx`
- `frontend/src/app/teacher/submissions/[submissionId]/review/page.tsx`
- `frontend/src/components/account-form.tsx`
- `frontend/src/components/app-shell.tsx`
- `frontend/src/components/assignment-briefs.tsx`
- `frontend/src/components/auth-provider.tsx`
- `frontend/src/components/document-analysis.tsx`
- `frontend/src/components/student-shell.tsx`
- `frontend/src/lib/navigation.ts`
- `frontend/tests/navigation.test.cjs`
- `frontend/tests/proxy.test.cjs`
