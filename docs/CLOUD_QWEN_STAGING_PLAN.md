# Forma — separate cloud Qwen staging plan

This is a plan only. Gate staging work on a successful explicitly approved local synthetic request, a settled provider-verified ledger charge, acceptable validated output, and review of the exact endpoint's privacy terms. No production Render, Neon, R2 or Cloudflare resource is changed by this work. Deployment and any further paid calls require separate authorization.

## Revisions and schema

Record the reviewed backend and frontend commit SHAs before staging. The backend revision must contain the shared OpenRouter transport, `assessment_configuration`, job-ID propagation and existing draft/publication support. The frontend can retain the Teacher Review Workspace revision; no UI revision is required specifically for the cloud provider. Deploy compatible review backend/frontend revisions together if staging predates Phase 4.2.

On an isolated staging PostgreSQL database, back up first and apply the repository's existing additive migrations: `006_document_understanding_jobs`, `007_submission_student_id_width`, `008_ai_budget_ledger` and `009_rubric_assessment`, plus preceding migrations as applicable. The provider extension adds no new migration or column. Verify migration idempotency, tables, foreign keys, and PostgreSQL reservation race tests against a disposable schema before enabling paid requests. Never point staging at production Neon. Retain ledger/history tables during rollback.

## Isolated resources and settings

Provision separately named staging backend/frontend services, database, private storage bucket and hostname; do not repoint production domains, change production Cloudflare records or reuse production R2 credentials. Begin with synthetic fixtures only, separate authentication/session secrets and restricted teacher accounts. Disable public registration and SMTP/email workers. Restrict staging access and verify tenant authorization and private document download/page routes.

Set backend `FORMA_DATABASE_URL` to the isolated staging PostgreSQL database; configure either staging-only private R2 credentials (`FORMA_STORAGE_BACKEND=r2`, `R2_ACCOUNT_ID`, `R2_BUCKET_NAME`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`) or an appropriate staging persistent local volume. Set `FRONTEND_ORIGIN` to the isolated staging frontend and retain existing cookie/proxy/security settings. Never expose database, storage or provider credentials to frontend env or build output.

Start with `FORMA_AI_PAID_ENABLED=false` and the worker disabled. Configure `FORMA_AI_PROVIDER=openrouter`, `FORMA_ASSESSMENT_PROVIDER=openrouter`, exact `FORMA_OPENROUTER_MODEL=qwen/qwen3-vl-8b-instruct`, `FORMA_OPENROUTER_ENDPOINT`, backend-only `FORMA_OPENROUTER_API_KEY`, privacy acknowledgement after review, and reviewed price caps. Keep `FORMA_AI_PAID_FALLBACK_ENABLED=false`, `FORMA_AI_MONTHLY_BUDGET_USD=4`, `FORMA_AI_MAX_JOB_COST_USD=0.02`, `FORMA_AI_MAX_CONCURRENT_REQUESTS=1`, `FORMA_DOCUMENT_CONCURRENCY=1`; remove Gemini credentials. Retain existing request timeouts/page/image/output bounds. Frontend needs only its server-side `FORMA_BACKEND_URL` targeting staging backend; no new browser env variable.

A $4 monthly cap applies to one ledger. If local and staging must share the same overall $4 allowance, do not give them independent $4 ledgers: stop local paid access and carry forward/reconcile all same-month liabilities into the authoritative staging ledger before activation, or keep using a single authoritative ledger. Keep the dedicated provider monthly key cap at or below $4 as a backstop. Do not reset accounting when promoting code, rotating keys or rolling back.

## Privacy and release checks

Confirm provider account privacy settings, exact endpoint identity, region, retention, training prohibition, ZDR support and key limits again at deployment time. Endpoint/pricing capabilities may change. Fail closed if routing constraints cannot be met. Synthetic-only is the staging default; real student data needs a separate institutional/privacy authorization before any transmission. Ensure prompts, PDFs, keys and model/provider error bodies do not enter logs or public artifacts. Existing app records retain source evidence and suggestions privately under existing authorization; provider routing settings do not remove those local records.

Run mocked workflow, budget and review regression suites on the candidate backend. Validate login, private PDF rendering, rubric approval, no AI-initialized teacher scores, draft persistence and explicit publication controls using saved data. With separate approval, enable paid inference for one synthetic staging request, then disable it until provider generation metadata and ledger match. Confirm month exposure, no overlapping paid reservations, no fallback, no automatic retry and no student-visible grade. Do not publish even synthetic grades as part of cloud verification.

## Rollback

First disable `FORMA_AI_PAID_ENABLED` and stop document workers on staging. Allow active requests to finish or retain them as unknown liabilities; disabling the flag cannot cancel a request already sent. Reconcile every in-flight/unknown charge before any re-enable. Keep the same database/ledger and generation IDs; never delete reservations to restore allowance.

Restore the recorded compatible backend/frontend revisions and staging environment. Leave additive tables intact; do not drop schema or erase teacher decisions/grades. Offline review can continue; use Ollama only where a local model service is available and deliberately configured. Queued jobs keep their snapshotted OpenRouter configuration, so changing defaults to Ollama alone does not convert them: leave paid disabled and explicitly resolve queued cloud jobs before restarting workers. Verify saved reviews and private originals, then investigate endpoint/billing failures before another approval. Production remains untouched throughout.
