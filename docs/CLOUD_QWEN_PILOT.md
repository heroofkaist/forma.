# Forma — local cloud Qwen pilot

The existing assessment engine now accepts `FORMA_ASSESSMENT_PROVIDER=ollama|openrouter`. It defaults to Ollama independently of `FORMA_AI_PROVIDER`, which selects document understanding. Optional rubric prose drafting remains local Ollama. There is no provider fallback or UI change. Existing rubric/evidence validation, saved suggestions, teacher decisions and deliberate publication remain in place.

Both cloud paths reuse `OpenRouterProvider` for structured completion, exact model `qwen/qwen3-vl-8b-instruct`, one explicitly selected endpoint, privacy preflight, token/price bounds, reservation, dispatch and receipt accounting. Jobs snapshot their provider, model, endpoint and options. Changing environment variables does not reroute queued jobs. The monthly ledger is shared across both purposes and all workers using the same database. Document understanding and assessment are separate jobs, each limited to $0.02; they do not share a combined $0.02 submission allowance.

The existing PostgreSQL advisory transaction lock serializes admission. Before each inference POST, a committed ledger reservation holds the entire remaining job allowance. The hard monthly cap is $4, the hard job cap is $0.02, and only one paid request can be in flight. Token estimates are conservative admission checks, not proof that a provider cannot overcharge. The dedicated provider monthly key cap is a second control; a reported overrun pauses paid inference. Missing receipts/timeouts retain liability for reconciliation. Invalid model output still costs money and is recorded before schema/evidence validation. No automatic request retry is added.

Routing retains `only`, `order`, `allow_fallbacks=false`, `require_parameters=true`, `data_collection=deny` and `zdr=true`. See [OpenRouter provider routing](https://github.com/OpenRouterTeam/docs/blob/main/guides/routing/provider-selection.mdx) and [ZDR documentation](https://github.com/OpenRouterTeam/docs/blob/main/guides/features/zdr.mdx). An operator must review the exact upstream endpoint, region, applicable terms and retention policy before acknowledging privacy. If it is unavailable, incompatible, too expensive or cannot meet privacy filters, the request fails; no alternative endpoint is selected.

## Local configuration

Use a dedicated local PostgreSQL database, local file storage and synthetic data only. Do not use a production database or proxy a local port to production. All paid workers sharing the key must use the same ledger; do not run separate pilot ledgers against the same key or reset/delete the ledger during a billing month. Never run the application worker concurrently with the smoke script.

Create a dedicated non-management OpenRouter key with a **monthly limit no greater than $4**, no BYOK usage, no shared production use, and provider privacy settings reviewed. Obtain the exact approved endpoint slug from model endpoint metadata; do not use a guessed slug or substitute a provider name. Keep secrets in the terminal/session or an ignored local file, never Git or frontend variables.

The smoke script requires a database named `forma_cloud_pilot` on `localhost`, `127.0.0.1` or `::1`, without URL query parameters. Create this empty database in your own local PostgreSQL instance first, for example `createdb forma_cloud_pilot`. Configure:

```sh
export FORMA_DATABASE_URL=postgresql://localhost/forma_cloud_pilot
export FORMA_OPENROUTER_API_KEY='<dedicated-key>'
export FORMA_OPENROUTER_MODEL=qwen/qwen3-vl-8b-instruct
export FORMA_OPENROUTER_ENDPOINT='<privacy-approved-exact-endpoint-slug>'
export FORMA_OPENROUTER_PRIVACY_ACKNOWLEDGED=true
export FORMA_OPENROUTER_MAX_PROMPT_USD_PER_MILLION=0.25
export FORMA_OPENROUTER_MAX_COMPLETION_USD_PER_MILLION=0.75
```

The script fixes local storage, disables dotenv, email and document workers, disables Gemini/fallback, and sets $4/month, $0.02/job and concurrency one. It never reads uploaded or existing student content. It creates a fixed synthetic force-calculation PDF, deterministic source observations and one criterion, then makes **one assessment inference POST** using the real engine. Document understanding is deliberately not invoked: testing both live stages would require at least two paid requests. The complete two-stage workflow is tested with mocks.

## One-command paid smoke test — approval required

No paid request was run during implementation. Obtain explicit user approval for this single synthetic request (up to $0.02) before running the following. The flag records that operator approval; invoking without it exits before database/network work.

```sh
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/smoke_cloud_qwen.py --approve-one-paid-request
```

Do not invoke this command merely to check configuration. `--help` is safe. Every approved invocation creates a new job and may incur another charge. No server, broad benchmark or deployment is involved. The script initializes the existing schema/migrations in the dedicated local database, saves an unverified suggestion, then queries generation metadata with a GET to verify the actual charge in the same ledger. It prints the job ID, reservation ID, model, endpoint, settled cost and `published=false`; it never creates teacher decisions or grades.

Verify the printed reservation in PostgreSQL:

```sql
SELECT j.id, j.context->>'task' AS purpose, c.provider, c.model,
       c.state, c.reserved_nusd, c.actual_usd, c.generation_id,
       c.prompt_tokens, c.completion_tokens
FROM ai_request_charges c
JOIN document_processing_jobs j ON j.id = c.job_id
ORDER BY c.created_at DESC;
```

For JSON columns on PostgreSQL, the query uses native JSON operators. Expected: exactly one new assessment charge, exact model, a generation ID and `state=settled`; `actual_usd` must agree with provider generation metadata. The final print comes only after successful reconciliation. Provider metadata can lag: if reconciliation fails, keep the existing receipt/reservation and retry **only the metadata command**, never inference:

```sh
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/reconcile_ai_billing.py --reservation '<reservation-id>'
```

On timeout, missing generation ID, refused/truncated output, invalid evidence or budget denial, inspect the printed job and ledger. A missing generation ID requires operator billing investigation; do not assume zero cost or clear its reservation. Receipt metadata can increase a previously recorded cost and trigger the existing overrun circuit. Actual cloud availability, output quality and real charges remain unverified until the user-approved live test succeeds.

## Running the existing local application afterward

Use your normal isolated local application runtime and synthetic course/submission fixtures, with `FORMA_AI_PROVIDER=openrouter`, `FORMA_ASSESSMENT_PROVIDER=openrouter`, the key/model/endpoint/privacy settings above, and `FORMA_AI_PAID_ENABLED=true`, `FORMA_AI_PAID_FALLBACK_ENABLED=false`, `FORMA_AI_MONTHLY_BUDGET_USD=4`, `FORMA_AI_MAX_JOB_COST_USD=0.02`, `FORMA_AI_MAX_CONCURRENT_REQUESTS=1`. Use the same dedicated PostgreSQL ledger, local storage, disabled email and one document worker. Frontend uses its existing same-origin proxy, e.g. `FORMA_BACKEND_URL=http://127.0.0.1:8000`; no key enters the browser. Stop the smoke script before starting the worker. Each explicit analysis/assessment action can make a new paid request; the single-request approval above does not authorize additional live calls.

For offline development set both provider selectors to `ollama` and `FORMA_AI_PAID_ENABLED=false`. The saved review workspace remains usable without any inference. `run_local_qwen.py` intentionally stays offline and overrides paid settings; it is not the cloud launcher.

## Verification

Mocked tests cover document understanding → rubric approval → assessment → saved suggestion → teacher decision, authentication, exact queued configuration, shared charges, committed reservations before POST, invalid evidence and JSON, uncertain receipts, no fallback and no automatic publication. The smoke procedure itself is exercised with mocked inference and independent generation metadata whose cost updates the ledger. PostgreSQL lock/race coverage uses a disposable local instance and schema, never Neon. See `test_openrouter.py`, `test_cloud_pilot.py`, `test_ai_budget.py`, `test_ai_budget_postgresql.py`, `test_assessment.py` and `test_review_workspace.py`.

The frontend is unchanged. No model benchmark, dependencies, production setting change or deployment is needed for this pilot. A separate [staging plan](CLOUD_QWEN_STAGING_PLAN.md) applies only after the approved live pilot succeeds.

Checks on 2026-10-15: **82 passed**, 21 existing dependency/lifecycle warnings, including the PostgreSQL race test on a newly initialized loopback-only PostgreSQL server. A separate mocked run exercised the smoke script against a fresh local PostgreSQL database: one inference POST, committed reservation before dispatch, saved suggestion, and independently reconciled mocked charge. These are synthetic receipts, not actual provider charges. The temporary PostgreSQL server was stopped afterward. `git diff --check` passed. No frontend files changed in this pilot.

```sh
# Point this only at a disposable local PostgreSQL instance; test creates/drops a unique schema.
FORMA_TEST_POSTGRESQL_URL=postgresql://localhost/postgres PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/test_cloud_pilot.py backend/tests/test_openrouter.py backend/tests/test_assessment.py backend/tests/test_ai_budget.py backend/tests/test_ai_budget_postgresql.py backend/tests/test_review_workspace.py backend/tests/test_ai_providers.py backend/tests/test_student_pdf_workflow.py -q
git diff --check
```
