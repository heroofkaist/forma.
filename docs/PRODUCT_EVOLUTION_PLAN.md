# Forma product evolution

## Repository audit and baseline

Next.js 15/React uses shared Russian academic styles, separate teacher and student shells, fetch helpers and client-side bearer tokens. OpenNext builds a Cloudflare Worker. FastAPI runs on Render's PORT; SQLAlchemy supports SQLite locally and Neon/psycopg in deployment; blob helpers use local disk or private R2. Gemini grades cropped images with validated criteria and teacher approval.

Working: persisted legacy assignments/questions/crops, PDF uploads, bounded image grading retries, teacher overrides, CSV export, reusable academic course offerings/families, PDF/DOCX academic submissions, deadlines/resubmissions, published-grade filtering, normalized English token passage matching with source offsets. Historical fixtures and demo grades are explicitly demo-mode dependent. Existing academic assignments correctly flush their legacy parent before inserting foreign keys.

Partial: enrollment codes and yearly reuse exist but codes have no lifecycle, capacity or approvals; authorization isolates student records but all legacy teachers share an administrative scope. Academic submissions lack automated Answer creation, so normal document submission does not produce a universal assessment. Originality is synchronous, English-only and scans every candidate in a course. Frontend contains hardcoded demo notices and physics/math subject normalization. Manual templates remain central to legacy grading. There is no PPTX extraction, reference knowledge base, durable queue, account/email lifecycle, audit log, quota or secure same-origin session layer.

Baseline executed before edits: backend virtualenv pytest: 25 passed, 1 skipped (external PostgreSQL); Next.js production build passed with socket permission. System python has no pytest. Run tests from backend, since imports are flat modules. User's existing .gitignore edit must be preserved.

## Critical debt and security

Never grant public accounts the existing environment teacher's shared administrative scope. New accounts need explicit ownership and membership checks on both academic and linked legacy routes. Keep legacy login during migration, without importing plaintext passwords. Use Argon2id and opaque revocable database sessions; proxy through same-origin HttpOnly cookies with Origin checks. Verification/reset tokens must be hashed, expiring and consumed atomically. Registration stays disabled unless transactional email and authenticated deployment are configured. Rate limits must survive process restart and must not trust arbitrary forwarding headers. Course codes must be cryptographically random and lifecycle changes cannot delete academic records.

Documents and reference content are untrusted input. Inspect signatures/OOXML content, bound archive expansion and page count, never execute code or macros. Keep all provider secrets server-side. Independent teacher workspaces must never share similarity sources. Student feedback must come from published grades only. Kazakhstan and other deployments require an explicit retention/deletion policy and local legal review; no compliance certification is implied.

## Additive migration and rollback

001 adds account/session/action-token/rate-limit tables and ownership/course-policy/enrollment-state/legacy-assignment-owner tables with foreign keys. Existing tables/data and IDs remain intact. New metadata lives in sidecar tables so no historic course needs a speculative owner backfill. A recorded migration runs transactionally and repeatedly without resetting schema. Existing initialization is retained for compatibility; future schema changes must be reviewed migrations. Backup Neon and R2 before deployment, rehearse on a restored database. Rollback application with registration disabled; retain additive tables and data. Do not drop them. Existing legacy administrator stays available until ownership is explicitly assigned by an operator.

## Phases and acceptance gates

1. Persistent verified accounts, email reset, revocable sessions, profile/security, same-origin proxy; private course creation, code preview/join, expiry/rotation/disable/capacity, approval/roster controls and isolation tests. Preserve administrator login and existing academic records. No public activation without real email configuration.
2. Universal assignment categories, deterministic PDF/DOCX/PPTX ingestion with structure and limits, private course materials, flexible rubric validation and template-free submission. Test malformed content, multi-page PDFs, OOXML expansion, limits and permissions. No PPTX visual rendering claim.
3. Durable PostgreSQL processing jobs; assignment-aware Gemini interpretation of bounded rendered pages; associations may span pages and be uncertain. Teacher corrections/version history. No invented OCR evidence.
4. Approved rubric proposals and provenance-preserving retrieval/evaluation; immutable suggestions plus reviewed/published grades, costs/timeouts/quotas, evidence validation. No automatic publishing.
5. Permission-aware opted-in historical corpus, indexed candidate retrieval, Unicode text matching, passage highlighting/exclusions and reviewer decisions. Similarity is not proof of plagiarism; no invented probability.
6. Refine dashboard/review/document UX, accessibility, audit/retention, retries/cancellation, production verification and operational documentation.

Each gate requires executed tests and builds, changed-file/migration report and explicit remaining limitations. Do not treat scaffolding as a completed phase. No Redis/Celery/paid worker or LibreOffice is mandatory. Durable workers can poll Neon and recover leases; free Render cold starts remain an operational constraint.

## Deployment compatibility

Keep Cloudflare/OpenNext, Render/FastAPI, Neon, R2 and Gemini. Same-origin frontend proxy uses private FORMA_BACKEND_URL (fallback current NEXT_PUBLIC_API_URL during migration); browser APIs use /api/backend. Secure cookies in production, no browser password/token persistence. Configure FRONTEND_ORIGIN exactly. Backend registration flag defaults off. SMTP delivery uses configured TLS service; disclose missing integration and fail closed. Deploy backend additive migrations before frontend. No production deployment or live database writes are part of local implementation checks.

## Verification requirements

Account registration/duplicate validation/hash/login/logout/expiry/reset/token replay/rate limiting; ownership across two educators; enroll duplicate/invalid/expired/rotated/capacity/approval/removal; private legacy resources and unpublished grades; repeated migration/startup; synthetic extraction fixtures. Run all legacy regressions and frontend type/production/OpenNext builds. External PostgreSQL/R2/email checks need staging credentials and must be reported as unverified until actually exercised.


## Implemented increment

Account/enrollment and document/manual-review changes are detailed in IMPLEMENTATION_REPORT.md. Four additive migrations now cover identity/ownership, structured documents/materials, immutable reviews/publication links and encrypted durable email delivery. The legacy product remains available. The next gate is Phase 3 full-document interpretation and durable processing; this report does not claim the six-phase target is complete.
