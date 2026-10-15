# Qwen engine with a strict monthly spending policy

Cloud inference is **disabled by default**. No paid request, purchase, deployment, production data change, provider-key creation or account-setting change was performed. The OpenRouter transport was tested with mocked HTTP only. The new local benchmark genuinely ran against this Mac's loopback Ollama daemon.

## Existing components and the missing connections

The repository already had private PDF upload/storage, deterministic PyMuPDF extraction, leased PostgreSQL jobs, immutable interpretations, strict page/question/evidence validation, teacher corrections and authorized original-PDF preview through the cookie BFF. The local Ollama adapter and Gemini adapter already shared a small provider interface. The missing pieces were cloud Qwen transport, durable financial accounting and a budget-pause/resume path. Authentication, enrollment, ownership/institution permissions, private R2 access and grade publication are unchanged.

`ai_providers/qwen.py` now owns the bounded page runner and `PageObservations` contract used by **both** Qwen adapters. Every selected page is rendered, including selectable-text pages; extracted text accompanies the images. The smaller model response maps into the existing Interpretation schema, which still rejects invented pages/question IDs, unsupported evidence and fabricated unreadable content. Observed transcription, proposed LaTeX and interpretation remain distinct in teacher review. There are no grades or correctness scores. Documents over the page/time budget explicitly list omitted pages and remain partial/review-required.

`openrouter.py` uses existing httpx with the fixed HTTPS API origin and exact model `qwen/qwen3-vl-8b-instruct`. It sends PNG data URLs in the request body, never public/private R2 URLs. Redirects and environment proxies are disabled. The transport has no fallback branch, tools, plugins, external image URLs or model list. Model/config snapshots and cache separation are retained; old jobs remain with their original provider. A new provider can implement the existing `Provider.interpret` protocol, map to the shared schema and supply its own audited accounting/privacy controls.

## What the budget ledger enforces

Additive migration **008_ai_budget_ledger** creates only `ai_budget_periods`, `ai_budget_controls` and `ai_request_charges`. Earlier migrations, submissions, originals and analysis versions are retained. Migration application is idempotent under the existing migration lock. Amounts use integer nanodollars, rounded upward, with the original decimal receipt also recorded. No prompts, images, keys, URLs, account/student identifiers or names are stored in this ledger; it references the existing opaque job UUID.

Before **each inference POST**, a separate transaction takes PostgreSQL advisory transaction lock `62401705`, checks the global pause, month exposure, active-call count, same-job exposure, configured caps and provider key credit, and commits a reservation. The application hard caps are $4/month, $0.02/job and one paid request at a time; environment values can reduce these caps. A month's initially recorded limit cannot be raised through subsequent reservations. SQLite uses a database writer lock for local/test equivalence; PostgreSQL uses the transaction lock across processes/instances sharing the database.

The admission estimate accounts for the actual bounded image dimensions, prompt/schema bytes and maximum output tokens at the selected endpoint's published token rates. Images are **not** assigned a fixed price. The estimate is not a mathematical tokenizer/preprocessing guarantee. Each call reserves the **entire remaining $0.02 job ceiling**, rather than just the estimate. This conservative hold prevents concurrent workers from selling the same remaining allowance. Current limits are:

| Cloud resource | Default | Hard maximum |
| --- | --- | --- |
| Pages/document and images/request | 3 / 3 | 3 / 3 |
| Image longest edge | 1120 px | 1400 px; PDF scale at most 1.5 |
| Extracted text/batch | 3000 characters | 3000 |
| Question context | 20 definitions, about 2000 characters | Same |
| User/system prompt | 16 KB / 8 KB UTF-8 | Same |
| Encoded request body | 12 MB | Same |
| Output tokens/request | 2200 | 3000 |
| Request/document inference time | 60 / 180 seconds | 90 / 180 seconds |
| Paid requests in flight | 1 | 1 |

Successful non-streaming receipts reconcile `usage.cost`, token usage, model and opaque generation ID. This happens before model-output parsing/validation, so invalid JSON or invalid evidence still incurs its real charge. Missing/invalid cost, unreadable HTTP responses, timeouts, errors after dispatch and crashes retain the full reservation as unknown. Expired reservations become unknown, **never free**. There is no automatic resend after ambiguous billing. Actual costs above a reservation pause all paid requests; higher corrected receipts can increase recorded liability, while a repeated receipt cannot reduce settled spend.

Retries spend the same job's remaining ceiling. Reanalysis creates a bounded new analysis version whose costs count toward the same global monthly budget, including any outstanding old-job liabilities. Settled charges reset for admission in the next UTC calendar month; unsettled/unknown liabilities carry into **every** future month until verified. Requests spanning a month boundary conservatively count in both reservation and reported billing months. There is no cron reset that deletes history.

HTTP 402, including preflight metadata failures, sets a persistent provider circuit and `awaiting_budget`. The worker never claims that state automatically, so Render wakeups/restarts do not generate rejection loops. Insufficient allowance and paid-disabled calls also pause. Original PDFs, submission records and prior analyses stay available for manual teacher review and existing manual grading. The teacher UI and student's status show the pause. Authorized teachers can explicitly resume the latest paused job with remaining attempts, subject to billing availability, rate limits and existing job/version limits. A teacher cannot clear the provider circuit or submit invented cost/refund information. Resuming is audited and keeps attempts; provider credit is checked again before an inference POST.

**Gemini compatibility:** its adapter, request implementation and schema fix remain, with offline SDK coverage. Its paid document calls and the separate legacy crop grader currently pause under this strict budget policy because they lack verified billed-cost/provider-key enforcement. This prevents an unmetered route around the shared $4 ceiling. Blank-key deterministic extraction remains explicitly labelled and does not claim handwriting inference. Selecting Ollama never calls Gemini or OpenRouter. No production bypass flag was added. Supporting paid Gemini again requires an audited provider-specific accounting implementation.

These controls prevent intentional overspending, but cannot guarantee a third party's final bill against billing delays, preprocessing differences, key misuse or service defects. The dedicated provider key limit is the final layer. Do not use that key elsewhere, run separate databases against it, attach upstream BYOK credentials, or enable any other paid AI service within the same $5 total without reducing the allocation accordingly.

## Provider protections and privacy before any cloud enablement

1. In the intended OpenRouter workspace, create a **dedicated inference key**, not a management key. Set its spending limit to **$4.00** with **monthly** reset. Disable automatic top-ups/auto-recharge in billing and avoid subscriptions/other paid features. Never enter a management key into Forma. The adapter checks current-key metadata before inference: finite limit <= $4, monthly reset, non-management identity, zero monthly BYOK usage and enough remaining key credit for the reservation. The API documents [key creation](https://openrouter.ai/docs/api/api-reference/api-keys/create-keys) and [current-key metadata](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key).
2. Verify the **cash checkout total**, taxes and fees before purchasing. OpenRouter currently documents a [$5 minimum credit purchase](https://openrouter.ai/terms) and [credit-purchase fees](https://openrouter.ai/docs/faq). A fresh $5 purchase plus fees may exceed this user's strict $5 total. The $4 inference cap does not fix that. If no funding option fits the total, stay on local Ollama; do not purchase or enable cloud inference. No purchase is required to run the mocked suite or local benchmark.
3. Disable BYOK for this dedicated workspace/key and other auto-routing/model-fallback configurations. Keep paid fallback false. Review [OpenRouter ZDR](https://openrouter.ai/docs/guides/features/zdr), the chosen provider's current retention/training policies, regional processing, institutional requirements and student-data permissions. Configure account-level ZDR and deny training/data collection. This code does not establish legal compliance.
4. Select **one exact endpoint tag** from the [model endpoint metadata](https://openrouter.ai/api/v1/models/qwen/qwen3-vl-8b-instruct/endpoints), after that privacy review. A public metadata check during implementation listed `parasail/bf16` at $0.25/M prompt and $0.75/M completion tokens. This is availability/pricing information, **not approval or proof of ZDR eligibility**. No endpoint is enabled by default. An empty endpoint fails closed; do not blindly copy that observed tag.
5. Every request enforces `provider.only=[exact-tag]`, the same `order`, `allow_fallbacks=false`, `require_parameters=true`, `data_collection=deny`, `zdr=true` and prompt/completion rate ceilings, with no additional per-request/image fee accepted. Endpoint metadata must support structured outputs. The [routing documentation](https://openrouter.ai/docs/guides/routing/provider-selection) defines these filters. If no endpoint satisfies all filters the call fails; the application does not relax privacy or change provider/model. Real private documents must not be used to discover policy compatibility.

## Deployment plan — only after separate approval

No Render/Cloudflare configuration was changed. The exact desired backend values below are a plan, **not** applied settings. First deploy/rehearse against a restored staging database with `FORMA_AI_PAID_ENABLED=false`. Preserve current Neon/R2/auth/SMTP configuration and Render's start command. Startup applies reviewed additive migrations including 008 under the existing migration lock; no manual submission alteration or data migration is needed. Verify migration repeatability and run the opt-in PostgreSQL tests against a dedicated test database before rollout.

After provider protections, checkout and privacy review, configure **Render backend secrets/environment only**:

```ini
FORMA_AI_PROVIDER=openrouter
FORMA_AI_PAID_ENABLED=false
FORMA_AI_MONTHLY_BUDGET_USD=4.00
FORMA_AI_MAX_JOB_COST_USD=0.02
FORMA_AI_MAX_CONCURRENT_REQUESTS=1
FORMA_AI_PAID_FALLBACK_ENABLED=false
FORMA_OPENROUTER_MODEL=qwen/qwen3-vl-8b-instruct
FORMA_OPENROUTER_API_KEY=<dedicated-inference-key-with-$4-monthly-limit>
FORMA_OPENROUTER_ENDPOINT=<one-exact-privacy-approved-endpoint-tag>
FORMA_OPENROUTER_PRIVACY_ACKNOWLEDGED=false
FORMA_OPENROUTER_MAX_PAGES=3
FORMA_OPENROUTER_BATCH_PAGES=3
FORMA_OPENROUTER_IMAGE_EDGE=1120
FORMA_OPENROUTER_OUTPUT_TOKENS=2200
FORMA_OPENROUTER_TIMEOUT_SECONDS=60
FORMA_OPENROUTER_MAX_PROMPT_USD_PER_MILLION=0.25
FORMA_OPENROUTER_MAX_COMPLETION_USD_PER_MILLION=0.75
FORMA_DOCUMENT_CONCURRENCY=1
FORMA_DOCUMENT_WORKER_ENABLED=true
GEMINI_API_KEY=
```

Keep `FORMA_AUTH_REQUIRED=true`, `FORMA_DEMO_MODE=false`, `FORMA_STORAGE_BACKEND=r2` and existing institution permissions. Never put the OpenRouter key in Cloudflare/Next `NEXT_PUBLIC_*`, Git, shell command arguments or frontend bindings. Cloudflare keeps only its existing `FORMA_BACKEND_URL`; deploy the frontend UI change after approval using the project's existing workflow. Render Free sleep can pause processing; memory/OOM and Neon transactions require staging verification. Render cannot reach the Mac's localhost; do not set Ollama there, expose it publicly or open a tunnel.

Only after explicit paid-test approval set `FORMA_OPENROUTER_PRIVACY_ACKNOWLEDGED=true` and `FORMA_AI_PAID_ENABLED=true`, then test **one synthetic document**. Inspect the ledger and provider Activity for matching costs/model and no fallback. No live OpenRouter comparison has been run. Old failed Gemini jobs retain their original provider; use **Repeat analysis** after fixing the configured provider to create a new bounded version for the same submission, preserving the failed history. Paused OpenRouter jobs use **Continue after budget review** once genuinely funded/reconciled. Do not delete jobs, ledger rows or submissions to restore allowance.

To stop paid inference set `FORMA_AI_PAID_ENABLED=false`. An already dispatched call can still be billed; account for it. Do not roll back to an application version that lacks the spending guard while leaving live keys or workers enabled. Keep all additive ledger/data tables on rollback.

## Billing reconciliation and explicit resume

`backend/scripts/reconcile_ai_billing.py` reads only the [generation billing metadata endpoint](https://openrouter.ai/docs/api/api-reference/generations/get-generation), never the prompt/completion content endpoint or inference endpoint. Run only with the intended private database/key supplied securely through the process environment; this script does not load `.env` or accept cost overrides.

```sh
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/reconcile_ai_billing.py --reservation <reservation-uuid>
```

It verifies generation identity, exact model and non-BYOK billing before reconciling actual total cost. A reservation without a generation ID cannot be safely resolved by this command; it remains held indefinitely, including across months. Investigate provider Activity/support without logging documents; no operator refund/expiry shortcut is supplied. This intentionally trades availability for budget safety.

After a provider 402, verify available credit without making a new purchase automatically, then explicitly clear that circuit:

```sh
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/reconcile_ai_billing.py --resume-provider
```

This verifies the capped monthly key via a metadata GET and refuses a zero balance. It does not clear a reported-cost-overrun circuit, refund unknown reservations or queue jobs automatically. An authorized teacher then invokes `POST /api/document-analysis/{submission_id}/resume` through the existing cookie proxy/UI. Provider metadata may lag; the worker rechecks it before spending. An exhausted three-attempt job needs the normal reviewed reanalysis flow and version quotas.

## Local benchmark and commands

Use the unchanged [Mac setup/local review instructions](QWEN_LOCAL_ENGINE.md), with `FORMA_AI_PAID_ENABLED=false`, `FORMA_AI_PROVIDER=ollama`, empty cloud/Gemini keys and loopback-only servers. The local launcher and benchmark explicitly override inherited paid enablement/key settings. No model is auto-pulled or substituted; do not load multiple large models on the 24 GB Mac.

```sh
ollama ps
ollama pull qwen3-vl:8b-instruct
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/benchmark_qwen.py --output artifacts/qwen-budget-phase/my-new-run
```

The successful real run is [run-01/report.json](../artifacts/qwen-budget-phase/run-01/report.json), with [raw responses](../artifacts/qwen-budget-phase/run-01/raw-responses.json), [memory samples](../artifacts/qwen-budget-phase/run-01/memory-samples.json) and [the synthetic PDF](../artifacts/qwen-budget-phase/run-01/synthetic-three-pages.pdf). It exercised real account login, template-free assignment, enrollment, upload, private storage retrieval, durable job, Qwen, immutable persistence and teacher review API in an isolated ignored SQLite/storage runtime. Earlier Phase A artifacts remain untouched. The three-page fixture was rendered and visually checked: typed equations/vector force diagram, generated handwriting-style continuation, mixed energy/inclined-plane diagram and blurred patch.

| Metric | Local Ollama, actual | OpenRouter |
| --- | --- | --- |
| Worker wall duration | 26.950 s | Not run; requires paid approval |
| Page 1 / 2 / 3 batch latency | 11.375 / 4.636 / 10.836 s | Not measured |
| Raw response schemas / final validation | 3 valid / passed | Mock transport passed; no model measurement |
| Rendered/analyzed/omitted pages | 3 / 3 / 0 | Same fixture can be used after approval |
| Prompt/output tokens | 4507 / 875 | Not measured |
| Peak sampled Ollama process RSS | 8,702,853,120 bytes (8.11 GiB) | Not applicable |
| API inference charge | Local only; no paid API | No call; no measured cost |
| Private original after retrieval | Byte match | Storage path covered by regression suite |

RSS is once-per-second sampled daemon/runner memory, not full-machine peak. Ollama-reported model allocation overlaps unified memory; do not add the figures. The model was unloaded afterward; the pre-existing loopback daemon remains running. Handwriting uses a font, not real handwriting. The model still omitted the deliberately blurred patch instead of reporting it separately. Coverage means pages were sent/rendered, not that every mark was understood. No accuracy percentage or real cloud cost is claimed. The raw model output is saved only by the synthetic benchmark observer; ordinary inference does not save raw prompts/responses in logs or the ledger.

## Changed files and verification

Changes for this budget phase:

- `backend/services/ai_providers/engine.py`, `ollama.py`, new `qwen.py`, new `openrouter.py`: interchangeable adapter selection, shared rendering/schema validation, bounded cloud transport and paid Gemini guard.
- New `backend/ai_budget.py`, `backend/budget_models.py`, `backend/migrations/__init__.py`, `backend/persistence.py`: atomic accounting, circuit state and additive 008 registration.
- `backend/document_processing.py`, `backend/analysis_api.py`, `backend/services/ai_grader.py`: durable budget pause, authorized audited resume, no unmetered legacy paid route.
- New `backend/scripts/reconcile_ai_billing.py`; `backend/scripts/benchmark_qwen.py`, `run_local_qwen.py`: metadata reconciliation and explicit local-only guards.
- New `backend/tests/test_openrouter.py`, `test_ai_budget.py`, `test_ai_budget_postgresql.py`; `conftest.py`, `test_accounts_courses.py`, `test_academic_seed.py`, `test_processing_diagnostics.py`, `test_gemini_request_compatibility.py`: cloud failures/privacy, billing/concurrency/rollovers, isolation, migration count and offline Gemini compatibility.
- `frontend/src/components/document-analysis.tsx`, `frontend/src/app/student/assignments/[assignmentId]/page.tsx`, `frontend/tests/proxy.test.cjs`: visible pause/resume and cookie/origin proxy regression.
- `.env.example`, `README.md`, `docs/QWEN_LOCAL_ENGINE.md`, this guide; synthetic `artifacts/qwen-budget-phase/run-01` (runtime secrets/database/object copies remain ignored).

Pre-existing local prototype changes to main.py, interpretation fields, processing diagnostics, AI provider tests, workflow tests and Phase A artifacts were retained. Schema-width migration 007 and PDF preview/security fixes were not replaced. No dependencies were added.

Run checks from repository root (PostgreSQL checks require a dedicated safe `FORMA_TEST_POSTGRESQL_URL`, never the production URL):

```sh
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
cd frontend
npm test
npx tsc --noEmit
npm run build
```

Live Gemini compatibility tests now additionally require `FORMA_TEST_PAID_ENABLED=true` and their explicit test key; they are not part of normal local-only testing. OpenRouter tests are always mocked. Actual OpenRouter model output/schema compatibility, available privacy-compliant endpoint, charges, checkout total and live Render/Neon/R2 operation remain external verification items. A local/mock pass is not a production guarantee.

## Verification on 2026-10-15

The full backend suite ran against a freshly initialized, disposable loopback PostgreSQL instance: **144 passed, 1 skipped**, with 21 dependency/lifecycle warnings. This includes the two-connection last-allowance race, additive migration repeatability, PostgreSQL lease behavior and existing database regressions. Only the explicitly opted-in live Gemini test was skipped. Without the dedicated PostgreSQL URL, the same suite reported 137 passed and 8 skipped. The temporary PostgreSQL server was stopped after verification; Neon and production records were not accessed.

This run exposed an existing demo-seed ID overflow in PostgreSQL. `backend/academic_api.py` now gives newly created synthetic legacy submissions IDs within the existing 36-character column; existing fixtures retain their references. `backend/tests/test_academic_seed.py` asserts that bound and passes on SQLite and PostgreSQL. These two files supplement the changed-file list above.

Frontend verification: **11 tests passed**, TypeScript checking and the Next.js production build passed. `git diff --check` passed.

A fresh real local run is saved in [verification-2026-10-15/report.json](../artifacts/qwen-budget-phase/verification-2026-10-15/report.json), alongside its synthetic PDF, raw responses and memory samples. Worker duration was **28.497 seconds**; page batch latencies were **12.792 / 4.648 / 10.954 seconds**. All three response schemas and final strict validation passed; 3 pages were analyzed, none omitted, and the immutable result remained `needs_review`. Prompt/output tokens were **4507 / 875**, sampled Ollama process peak RSS was **8,675,229,696 bytes**, and private retrieval matched the original PDF bytes. The same handwriting/blurred-patch limitations described above apply. The model was unloaded afterward. No paid inference, purchase or deployment occurred.
