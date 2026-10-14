# Product evolution implementation report

## Phase 1 — implemented locally, deployment validation pending

Persistent Argon2id accounts support registration, verification, login/logout, reset, profile and password changes. Verification/reset actions are single-use and expire; sessions have absolute expiry and database revocation. New browser sessions use a same-origin proxy with HttpOnly cookies and Origin enforcement. Rate limits survive restart. Registration defaults off until authenticated deployment, real TLS SMTP and the outbox encryption key are configured. Encrypted, durable email delivery has bounded retries and lease recovery; the UI/API truthfully reports queued mail.

Each verified account can create its own course, with course-scoped ownership and student membership instead of permanent global educator privileges. Code preview/join, approval, capacity, opening/closing times, rotation, disable, removal/suspension and roster CSV are functional. Joins serialize against the offering for idempotency. Private academic and linked legacy resources are checked on the backend; list queries are filtered as well. Student/teacher dashboards show relevant work, and one account can use both experiences. Existing environment administrator/student credentials and historical IDs remain available. Explicit operator course claims are documented; legacy student identity mapping remains a separate migration.

Migration 001 adds accounts, sessions, email actions, rate buckets, course ownership, offering policies, enrollment states and legacy assignment ownership. Migration 004 adds the encrypted email outbox. Neither imports environment passwords or seeds production users.

## Phase 2 — implemented document/manual review workflow

Academic categories include problem sets, essays, laboratory reports, presentations, research reports, programming and general documents. Teachers can edit numeric rubric criteria with backend total/duplicate-ID validation. Submission is template-free. Deterministic extraction inspects real file contents, bounds processing, preserves PDF pages/regions, DOCX paragraphs/tables and PPTX slide text/tables. Source files/ZIP archives are restricted to static UTF-8 review and never executed. Originals remain in private R2, with structure/content hashes stored in PostgreSQL.

Course material upload/list/download supports private or student-visible content, tags, warnings and processing state. Students cannot list or download private solutions. Teacher document review has original download/PDF view, page/section navigation, extracted text, warnings, rubric scoring, comments and immutable review versions. Publication is explicit. A reassessment does not change a student's published result until republished. Published rubric feedback removes private reference solutions. The old cropped-image Gemini workflow remains available separately.

Migration 002 adds structured submission documents and course materials. Migration 003 adds immutable document review history and the published-review link. Existing tables and foreign keys remain intact.

## Executed verification

Baseline: 25 backend tests passed; one PostgreSQL test skipped. Next.js production build passed after permitting the localhost socket used by OpenNext.

Latest verification results are updated at the end of this file. Synthetic fixtures cover account/email/session lifecycle, rate limits, two independent educators/institutions, code lifecycle, approvals/capacity, removed memberships, linked legacy access, material privacy, malformed uploads, extraction limits, rubric bounds, review history and published-grade privacy. SQLite foreign keys are enabled in new platform tests. PostgreSQL tests use an isolated transactional schema when FORMA_TEST_POSTGRESQL_URL is configured.

An executed HTTP smoke test through the **built Next.js server → actual BFF route → isolated FastAPI/temporary SQLite** passed login cookies, course creation, join, PDF submission, saved review, hidden drafts, explicit grade publication, session revocation and CSRF rejection. Only synthetic local records were used. No production database or services were changed.

Visual browser inspection was attempted, but the available native browser was actively in use and computer-use actions were rejected on a changed window state. No screenshot-based visual QA is claimed. The UI retains existing styles and layouts; responsive appearance still needs a browser review.

## Remaining work and limitations

Phase 3 is the next implementation gate: durable PostgreSQL document-processing jobs, bounded Gemini full-document interpretation, uncertain multi-page answer association and teacher correction tools. Current extraction does **not** recognize handwriting or confidently associate question answers. Scanned/blank pages are flagged. Current universal assessment is manual teacher review; the existing Gemini crop grader is retained.

Phase 4 still requires reviewed AI rubric generation, material passage retrieval, source-evidence validation, universal AI suggestions, usage/cost accounting and quotas. Phase 5 still requires indexed originality candidate retrieval, authorized corpus/retention policies, Unicode matching and more complete exclusions. Existing similarity remains normalized English lexical matching within a course; candidate comparisons are capped at 100 recent eligible documents, not web-wide or semantic coverage. Phase 6 requires further visual/accessibility QA, audit-event coverage, retention/deletion operations and production staging validation. Pass/fail/qualitative grading strategies and a guided draft/publish assignment wizard are not implemented.

PPTX visual rendering/delivery evaluation and DOCX page-number rendering are unavailable. Document extraction and bounded legacy similarity execute during submission (extraction uses a thread pool); AI processing has not been added to this request path. The old crop-grading queue is still process-local. Course co-teacher/organization membership management is not yet exposed. Legacy copied bearer tokens remain valid until their existing expiry; the migration guide describes this exception and cutover.

Live SMTP delivery, Neon migrations, R2 and production Worker runtime have not been verified with staging credentials. Registration must remain off until those checks are completed. Deployment retains Render PORT, Neon/psycopg, private R2, Gemini and Cloudflare/OpenNext. No mandatory paid infrastructure or LibreOffice was introduced. See ACCOUNT_MIGRATION_AND_DEPLOYMENT.md for configuration and rollback.

## Final verification results

- Backend: **50 passed, 2 skipped**. Both skips require `FORMA_TEST_POSTGRESQL_URL`; no live PostgreSQL success is claimed. The full isolated suite includes concurrent submission serialization, adversarial role query parameters, expired/replayed email actions, encrypted outbox recovery and processing-request rate limits.
- Browser proxy unit tests: **5 passed** (`npm test`).
- TypeScript: **passed** (`npx tsc --noEmit`).
- Next.js production build: **passed**.
- Cloudflare/OpenNext packaging: **passed**, generated `.open-next/worker.js` using the existing Wrangler configuration.
- Built frontend/isolated backend HTTP smoke workflow: **passed**.
- Diff whitespace validation: **passed**.

A configuration change during work caused an unisolated legacy test collection to attempt a deployment database connection; it failed before connection. Added `backend/tests/conftest.py` so tests always initialize temporary SQLite/local storage and disable external providers before importing the app. All final results above use this isolation. Existing FastAPI lifecycle and dependency deprecation warnings remain.

## Changed files

The list excludes the user's pre-existing `.gitignore` change. No `.env` secrets were modified or copied.

- `.env.example`
- `README.md`
- `backend/academic_api.py`
- `backend/account_models.py`
- `backend/accounts.py`
- `backend/assignment_api.py`
- `backend/auth.py`
- `backend/courses.py`
- `backend/document_models.py`
- `backend/document_review.py`
- `backend/email_delivery.py`
- `backend/main.py`
- `backend/materials.py`
- `backend/migrations/__init__.py`
- `backend/permissions.py`
- `backend/persistence.py`
- `backend/requirements.txt`
- `backend/scripts/claim_legacy_course.py`
- `backend/services/document_ingestion.py`
- `backend/tests/conftest.py`
- `backend/tests/test_academic_seed.py`
- `backend/tests/test_accounts_courses.py`
- `backend/tests/test_document_ingestion.py`
- `docs/ACCOUNT_MIGRATION_AND_DEPLOYMENT.md`
- `docs/IMPLEMENTATION_REPORT.md`
- `docs/PRODUCT_EVOLUTION_PLAN.md`
- `frontend/.env.example`
- `frontend/next.config.mjs`
- `frontend/package.json`
- `frontend/src/app/api/backend/[...path]/route.ts`
- `frontend/src/app/forgot-password/page.tsx`
- `frontend/src/app/globals.css`
- `frontend/src/app/login/page.tsx`
- `frontend/src/app/page.tsx`
- `frontend/src/app/register/page.tsx`
- `frontend/src/app/reset-password/page.tsx`
- `frontend/src/app/settings/profile/page.tsx`
- `frontend/src/app/settings/security/page.tsx`
- `frontend/src/app/student/assignments/[assignmentId]/page.tsx`
- `frontend/src/app/student/courses/[offeringId]/page.tsx`
- `frontend/src/app/student/grades/page.tsx`
- `frontend/src/app/student/join/page.tsx`
- `frontend/src/app/student/page.tsx`
- `frontend/src/app/teacher/assignments/[assignmentId]/submissions/page.tsx`
- `frontend/src/app/teacher/courses/[offeringId]/assignments/page.tsx`
- `frontend/src/app/teacher/courses/[offeringId]/students/page.tsx`
- `frontend/src/app/teacher/courses/new/page.tsx`
- `frontend/src/app/teacher/page.tsx`
- `frontend/src/app/teacher/submissions/[submissionId]/review/page.tsx`
- `frontend/src/app/verify-email/page.tsx`
- `frontend/src/components/account-form.tsx`
- `frontend/src/components/app-shell.tsx`
- `frontend/src/components/auth-provider.tsx`
- `frontend/src/components/course-materials.tsx`
- `frontend/src/components/student-shell.tsx`
- `frontend/src/lib/academic.ts`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/platform.ts`
- `frontend/src/lib/types.ts`
- `frontend/tests/proxy.test.cjs`
- `render.yaml`
