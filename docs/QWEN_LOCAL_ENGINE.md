# Local Qwen3-VL document engine — Phase A

The later [strict-budget/OpenRouter phase](QWEN_BUDGET_AND_OPENROUTER.md) adds migration 008 and cloud accounting. This Phase A report retains its original measured results. Gemini code remains available, but unmetered paid Gemini calls are now paused under that policy; the local Ollama workflow below remains available.

## Architecture and safety

The original pipeline already provided secure multi-page upload, private local/R2 originals, deterministic PyMuPDF extraction, PostgreSQL jobs with leases/retries, immutable interpretation/correction records, and authorized teacher PDF review. Its worker invoked Gemini directly. This change adds a small provider protocol and immutable provider configuration in each new job's existing JSON context. Provider/model/prompt/budget settings participate in job/cache identity. Existing jobs without that snapshot remain Gemini jobs; changing an environment variable does not silently change their provider.

`services/ai_providers/engine.py` selects an adapter. `GeminiProvider` preserves the existing implementation and its schema compatibility fix. `OllamaProvider` uses existing httpx against native `/api/chat`; no new dependencies/frameworks are installed. Unknown provider names fail closed. An Ollama error never invokes Gemini. For compatibility, deployments without FORMA_AI_PROVIDER keep their existing Gemini behavior; local setup explicitly selects Ollama and blanks the Gemini key. The setting governs document understanding; legacy crop grading is separate and is not used by this prototype.

Ollama addresses are restricted to HTTP loopback, with no credentials, path, query, redirect following or environment proxy. Cloud model tags are refused. The adapter checks that the local model supports vision and refuses to start while another local model is loaded; it does not stop somebody else's model. A process lock plus durable-job concurrency restriction permits one local analysis at a time. Each request uses one configured model, retained briefly across page batches and explicitly unloaded after the document, including failure cleanup. A failed unload leaves the requested one-minute expiry in place.

Render's localhost is Render itself. It cannot reach this Mac's loopback server. Do not copy local Ollama settings to Render, open firewall ports, bind Ollama to 0.0.0.0, or tunnel its API publicly. This implementation and benchmark are local only. Render, Cloudflare, production data/roles, SMTP and credentials were not changed; no deployment or paid inference was performed.

## Model output and teacher review

Every budgeted PDF page is rendered, including pages with selectable text. PyMuPDF extraction is supplied alongside image data. One bounded batch is held at a time. The provider prompt treats uploads as untrusted data, disallows tools/code/grading and distinguishes `observed_text` from normalized `latex` and proposed `interpretation`.

Qwen has a smaller page-observation schema. Its model output must pass that schema first. The adapter assigns deterministic unique section IDs from batch/page order, maps observed_text to Forma transcription, aggregates question associations and passes the existing strict evidence/page/question validator before persistence. It never repairs arbitrary JSON, invents unseen pages or accepts unknown question IDs. Visual transcription remains unverified; exact embedded-text quotes are checked against source extraction. Unreadable/missing observations cannot contain invented text, LaTeX or interpretation. Teacher confirmation is never assigned by the model. The shared schema adds optional LaTeX/interpretation fields; existing records remain readable without migration.

The existing review panel now displays provider/model, partial-analysis state, observed text, editable LaTeX and separately labelled model interpretation. Existing PDF preview/page controls, correction versions, role checks and manual confirmation are reused. Document interpretation never creates or publishes a grade.

## Resource defaults for a 24 GB Mac

| Setting | Default | Hard cap |
| --- | --- | --- |
| Model | qwen3-vl:8b-instruct | One loaded local model |
| PDF pages analyzed/document | 3 | 6 |
| Pages/request | 1 | 2 |
| Image longest edge | 1120 px | 1400 px; no more than 1.5x PDF scale |
| Ollama context | 8192 tokens | 8192 |
| Output/request | 2200 tokens | 4096 |
| Request timeout | 120 seconds | 180 seconds |
| Document inference budget | 480 seconds | 900 seconds |
| Local concurrency | 1 | 1 |

Source text is bounded to 3000 characters per batch; question context to 20 definitions and a small text budget. Truncation is disclosed. Additional document pages are listed in `usage.omitted_pages` and in a PARTIAL ANALYSIS warning; the job remains `needs_review`, with `partial=true` exposed in status. There is no silent successful completion of an over-budget document. The existing upload limit remains 30 MB/50 pages. Transient connection/timeouts/429/5xx use the existing bounded durable retries; malformed output or invalid evidence fails for review. Job leases are renewed before each local batch and remain fenced by owner/expiry. Paid failover is absent.

These limits are a starting point, not a universal memory guarantee. Other desktop applications share the Mac's unified memory. RSS and Ollama allocation figures must not be added as if independent physical memory measurements.

## Exact Mac setup and benchmark commands

Run from the Forma repository root. Ollama must already be installed (the machine used here had a loopback daemon and CLI). Use the [official Mac installation](https://docs.ollama.com/macos) if needed. The model's [official library entry](https://ollama.com/library/qwen3-vl:8b-instruct) identifies the vision-capable local instruct tag; do not substitute its cloud/thinking tag.

```sh
ollama --version
ollama ps
ollama pull qwen3-vl:8b-instruct
```

Do not load it alongside another large model. If Ollama is not already running, start it in a separate terminal with a loopback bind and one-model/one-request limits:

```sh
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_NUM_PARALLEL=1 ollama serve
```

If the desktop app already owns port 11434, use that daemon rather than starting another one; the adapter still checks loaded models. Stop your own unused model explicitly with `ollama stop MODEL` before benchmarking if needed.

Install existing project requirements if the virtual environment is not already available:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
```

Run the complete synthetic workflow into a **new directory**:

```sh
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/benchmark_qwen.py --output artifacts/qwen-phase-a/my-run
```

The script refuses an existing benchmark database. It generates the three-page PDF, uses an isolated SQLite database/private storage directory, seeds clearly synthetic verified institution/teacher/student fixtures, logs in through the real auth API, creates a template-free assignment, enrolls the student, uploads the original, runs the durable worker with real Qwen and reads the teacher interpretation/original endpoints. It never loads the repository .env; its dedicated environment disables SMTP, registration, legacy credentials, Gemini and background workers. Synthetic raw model responses, job/review results and memory samples are saved only under that output directory. No arbitrary/private input path is accepted. The generated database, private object copy and runtime environment are gitignored. The local launcher validates the SQLite/storage paths and overrides inherited database settings before importing the application; it cannot launch a PostgreSQL/production runtime.

To inspect that actual analyzed submission in the UI, start the local backend using the generated isolated configuration:

```sh
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/run_local_qwen.py --runtime-file artifacts/qwen-phase-a/my-run/runtime.env
```

In another terminal:

```sh
cd frontend
npm ci
FORMA_BACKEND_URL=http://127.0.0.1:8000 npm run dev -- --hostname 127.0.0.1
```

Open http://localhost:3000/login. Use localhost in the browser: Next development canonicalizes its internal request origin to localhost; using a 127.0.0.1 browser Origin can be rejected by the unchanged same-origin mutation policy. The servers still bind only to loopback. Synthetic credentials are `local-teacher@example.test` or `local-student@example.test`, password `Forma-local-benchmark-only-123`. These accounts exist only in the generated database. Teacher: open Review queue or the synthetic assignment's Works and review page. Student: open the synthetic course/assignment. The review URL is `/teacher/submissions/<submission_id from report.json>/review`. HttpOnly-cookie proxy authentication and private PDF retrieval are unchanged. Keep the backend/frontend bound locally. Do not reuse these fixtures/passwords in production.

For ordinary local work, use a separate ignored environment file with the same isolated database/storage/auth values and:

```ini
FORMA_LOAD_ENV_FILE=false
FORMA_AI_PROVIDER=ollama
FORMA_AI_PAID_ENABLED=false
FORMA_OPENROUTER_API_KEY=
FORMA_OLLAMA_BASE_URL=http://127.0.0.1:11434
FORMA_OLLAMA_MODEL=qwen3-vl:8b-instruct
GEMINI_API_KEY=
FORMA_DOCUMENT_CONCURRENCY=1
```

`FORMA_LOAD_ENV_FILE=false` prevents main.py from filling missing local settings from the repository's production-oriented .env. Existing deployments retain the default dotenv behavior. No real .env was edited.

## Benchmark evidence

The fixture combines typed equations and a vector force diagram on page 1, handwriting-style generated equations/solution continuation on page 2, and typed energy work, an inclined-plane diagram and deliberately blurred image patch on page 3. Generated handwriting fonts are not genuine student handwriting and do not establish real handwriting accuracy.

The first real run (`artifacts/qwen-phase-a/run-01`) failed strict validation because Qwen reused a question ID as multiple section IDs. Its raw response and failed history are retained. The adapter-specific observation schema resolves this by assigning section IDs in application code; it does not relax page/evidence validation. The final adapter's successful run is [run-02/report.json](../artifacts/qwen-phase-a/run-02/report.json), with [raw model responses](../artifacts/qwen-phase-a/run-02/raw-responses.json), [memory samples](../artifacts/qwen-phase-a/run-02/memory-samples.json), [synthetic PDF](../artifacts/qwen-phase-a/run-02/synthetic-three-pages.pdf) and [actual local proxy verification](../artifacts/qwen-phase-a/run-02/http-review-check.json).

| Measured result | run-02 |
| --- | --- |
| Whole worker duration | 26.339 seconds |
| Batch latency (pages 1 / 2 / 3) | 10.665 / 4.673 / 10.890 seconds |
| Actual prompt / generated tokens | 4507 / 875 |
| Raw response schema validation | Three valid responses |
| Final strict evidence validation | Passed; immutable version saved; needs_review |
| Pages rendered / omitted | 3 / 0 |
| Peak sampled Ollama-process RSS | 8,479,244,288 bytes (7.90 GiB) |
| Peak API-reported model allocation | 6,718,215,945 bytes (6.26 GiB) |
| Source bytes after private retrieval | Match original |

RSS includes sampled Ollama daemon/runner processes; the API allocation includes model/accelerator memory and overlaps unified memory. Neither is whole-machine peak consumption. Sampling is once per second and can miss transient peaks. The local model was Q4_K_M, context 8192, on this 24 GB Apple M5 Pro Mac (Ollama 0.40.4); no multi-model run occurred and the model was unloaded afterwards.

Observed output linked page 1 and the handwriting-style continuation on page 2 to q1, mapped page 3 to q2, returned LaTeX for typed equations and separate descriptions for the force/inclined-plane diagrams. It omitted the deliberately blurred patch instead of flagging a separate unreadable fragment. Visual completeness and handwriting accuracy are therefore **not** established. These are observations from saved output, not accuracy statistics.

An actual local Next server/BFF was also exercised over HTTP: teacher cookie login succeeded with HttpOnly, analysis GET returned 200/one version, and private PDF GET returned 200/application/pdf with matching bytes. The browser automation surface was unavailable, so visual rendering was not inspected. This is an API/integration check, not a visual QA claim.

## Adding another model later

Add one adapter implementing `Provider.interpret(DocumentRequest, progress, observe)` plus an explicit configuration branch. Map provider-specific observations into the shared Interpretation schema, retain strict evidence validation, register a distinct version and test timeout/privacy/invalid output/cache separation. A local model with the same Ollama vision contract can first be evaluated by explicitly setting FORMA_OLLAMA_MODEL after pulling it; never run multi-model consensus or implicit provider selection. A different transport needs only its adapter. Keep rendering, private storage, jobs, permissions and review APIs independent of the model. Future richer localization can add an explicitly validated evidence type; it should not be inferred from nonexistent bounding boxes.

## Official API references

The native [vision API](https://docs.ollama.com/capabilities/vision) uses base64 images in user messages. [Structured outputs](https://docs.ollama.com/capabilities/structured-outputs) accept a JSON schema through `format`; local application validation remains required. [Chat API](https://docs.ollama.com/api/chat) documents stream=false, keep_alive and returned token/duration measurements. See the [Ollama FAQ](https://docs.ollama.com/faq) for local server and memory/concurrency configuration.

## Changed files and final checks

- `backend/services/ai_providers/engine.py`, `__init__.py`, `ollama.py`: provider protocol, configuration snapshots, preserved Gemini adapter and bounded local vision adapter.
- `backend/document_processing.py`: provider dispatch/cache identity, local concurrency, lease renewal, partial-cache exclusion and local HTTP retry classification.
- `backend/services/document_understanding.py`: optional separately labelled LaTeX/interpretation plus strict unreadable-content validation; existing Gemini implementation retained.
- `backend/analysis_api.py`: provider/partial metadata in authorized status responses.
- `frontend/src/components/document-analysis.tsx`: provider/model/partial state and separate editable observed/interpretation/LaTeX fields.
- `backend/main.py`, `backend/persistence.py`: optional dotenv opt-out and isolated local storage directory setting; defaults preserved.
- `backend/services/processing_diagnostics.py`: numeric local HTTP status without response/URL logging.
- `backend/scripts/benchmark_qwen.py`, `run_local_qwen.py`: synthetic benchmark and guarded local-only launcher.
- `backend/tests/test_ai_providers.py`: selection, snapshot retention, loopback/privacy, bounded rendering, invalid JSON, invalid evidence, truncation, timeouts, unavailable server/requeue and authorized review integration.
- `backend/tests/conftest.py`, `test_document_processing.py`, `test_processing_diagnostics.py`, `test_student_pdf_workflow.py`: isolated configuration and mocks at the new provider boundary.
- `.env.example`, `.gitignore`, `README.md`, this guide: explicit local configuration, ignored private runtime/database copies and setup documentation.
- `artifacts/qwen-phase-a/run-01` and `run-02`: generated benchmark PDFs, real raw responses, measured results and memory samples; only synthetic, non-secret artifacts are tracked.

Final validation: backend **108 passed, 7 skipped** (six PostgreSQL checks without a dedicated safe database URL; one opt-in Gemini live check without a test key), 21 dependency/lifecycle deprecation warnings. Frontend **10 passed**; TypeScript checking, Next.js production build and `git diff --check` passed. The local Qwen benchmark and real local proxy check are separate from the mocked regression suite and genuinely ran. No new OpenNext/production deployment was performed. Temporary local web servers were stopped after verification; the pre-existing Ollama daemon remains running with no model loaded.
