# Document analysis failure investigation

## Findings and confirmed fixes

The reported production exception cannot be identified from HTTP 201/200 and the old generic failure message. HTTP 201 confirms receipt/storage/queue creation; polling HTTP 200 confirms authorized metadata retrieval. Neither means Gemini or analysis persistence succeeded. No production logs, credentials, database records or private PDFs were accessed during this investigation.

Confirmed defects in local code:

- `document_processing.process_one()` converted exceptions into a safe but generic job failure with no server diagnostic.
- `start_worker()` silently discarded exceptions escaping the job handler, including claim failures and errors while saving failure state.
- Retry classification omitted botocore service/transport exceptions. R2 throttling/5xx and endpoint/read-timeout failures could become terminal despite being transient. These now use the existing three-attempt backoff budget. Selected PostgreSQL disconnect/serialization/deadlock operational errors are likewise retried. Missing objects, access denial and schema/constraint errors remain terminal.
- The cache insertion handler suppressed every IntegrityError as if it were a duplicate cache key. It now suppresses only a confirmed existing cache entry; unrelated integrity failures roll back the interpretation transaction and are logged.

No production root cause is claimed. In particular, local offline SDK schema conversion/request/response parsing passed; there is no evidence to blame Python 3.14 or an unsupported response schema.

## Pipeline traced

1. Authenticated `POST /academic/assignments/{id}/submissions` checks student/enrollment/availability/resubmission permissions. File validation and deterministic extraction run in a thread pool during upload. Originals are stored by the existing private R2 helpers. The submission, extraction/hash and durable job are committed together. A quota rejection preserves the receipt and marks analysis not scheduled.
2. The startup daemon polls `process_one()`. Claim uses the existing PostgreSQL advisory lock, conditional UPDATE RETURNING, global concurrency cap, attempt increment and five-minute lease. Expired leases recover; maximum attempts remain three. No changes to existing jobs are made by this code change itself.
3. The worker loads immutable context and stored extraction, reads the original through private R2 `get_object`/stream read/close and verifies SHA-256. Historical submissions without extraction run ingestion and persist its result. Page/unit budgets are checked.
4. A lease-fenced transition marks interpreting. The offering-scoped cache is checked. A cache miss invokes Gemini with existing configured model/key, bounded source text and image-only PDF rendering. Rendering, request preparation, SDK request, response JSON decoding and evidence validation have distinct diagnostic stages. Content/association validation remains strict; no fabricated output or grade fallback was added.
5. In a new transaction, the worker checks the same unexpired lease under row lock, inserts immutable interpretation, optionally inserts the cache entry, clears errors/lease and marks `needs_review`. Teacher confirmation later marks completed; it does not publish a grade.
6. On failure, the diagnostic is written **before** any attempt to update the database. Retryable errors queue the same job with backoff; terminal errors mark it failed using the existing safe client message. A failure-state write error is separately logged; its lease remains recoverable instead of pretending that the state update succeeded. Late workers still cannot overwrite a new owner or completed result.

## Diagnostic format and privacy

The `forma.document_processing` logger emits JSON error events via normal server stderr logging. No logging infrastructure/configuration changes are required. Events contain `event=document_processing_error`, job ID (null if claiming failed before a job was known), stage, exception type, classification, retryable flag and a sanitized traceback. Stages include `claim`, `load_job`, `source_read`, `source_hash`, `extraction`, `extraction_persist`, `processing_limits`, `interpret_transition`, `cache_lookup`, `pdf_render`, `request_prepare`, `gemini_request`, `response_decode`, `response_validate`, `analysis_persist`, `failure_persist` and `worker_loop`.

Tracebacks contain only code module basename, function and line number, plus exception-chain types. They omit source lines, local variables, absolute paths and all exception messages. Provider numeric HTTP status, allowlisted R2 error codes/status and PostgreSQL SQLSTATE are included when available. Raw SDK/provider response bodies, SQL/parameters, file/object names and keys, account identity, document contents, signed URLs, credentials, cookies and tokens are never passed to this logger. Raw `exc_info`/`logger.exception` is deliberately avoided because those can expose private payloads through exception strings. Client API responses retain safe messages, not tracebacks.

## Safe retry and retained data

After resolving the diagnosed dependency/configuration issue, an authorized teacher can use **Repeat analysis** on the existing submission review page. It invokes `POST /api/document-analysis/{existing_submission_id}` with `{"reanalyze":true}`. This creates a new bounded analysis version for the same submission, preserves the failed job/history and uses the original private PDF. Repeated requests converge on an active job. Students and unrelated teachers cannot invoke it. Existing limits remain 20 jobs/requester/day and three versions/submission/day; do not delete submissions/jobs to bypass limits. Automatic transient retries reuse the same job. Remote model calls remain at-least-once if a process dies after receiving a response but before committing it.

## Production verification still required

After a separately approved backend release, reproduce using a synthetic PDF and read Render error events for the job ID. Check the stage, exception type, final traceback frame and safe status/code. A `gemini_request` 400/401/403/404 needs provider model/configuration inspection; `response_validate` needs examination of model-output compatibility with the strict schema/evidence rules using synthetic input; `source_read` with AccessDenied points to storage authorization; `analysis_persist` with SQLSTATE identifies a database error class. These are diagnostic branches, not assertions about this production incident.

The deployed dependency versions and runtime can differ from local unpinned ranges. Local verification used Python 3.14.7, google-genai 1.75.0, SQLAlchemy 2.1.4, PyMuPDF 1.28.2 and psycopg 3.3.6. The real SDK was exercised through an offline fake HTTP transport, not live Gemini. Production model availability, credentials, quota, output validity, private R2 reads and actual PostgreSQL lease/transaction behavior still need staging/production evidence.

Render Free sleeping/restarts can pause processing. An operating-system OOM/SIGKILL cannot produce a Python traceback; correlate process restarts/memory events and lease exhaustion separately. PDF image encoding, source bytes and model serialization consume memory despite current budgets. No memory-limit or infrastructure change is made based on this hypothesis. Database outages can also prevent recording a failure; the new independent server logging covers the Python exception even in that case.

## Changed files and checks

- `backend/document_processing.py`: stage instrumentation, safe error logging, retry classification and failure-state recovery logging, narrowed cache conflict handling.
- `backend/services/document_understanding.py`: instrumentation around rendering, request preparation, SDK invocation, decoding and validation.
- `backend/services/processing_diagnostics.py`: structured allowlisted logger with sanitized exception-chain frames.
- `backend/tests/test_processing_diagnostics.py`: storage/missing/hash/provider/JSON/schema/persistence errors, claim/loop/failure-state logging, privacy, offline real SDK, safe retries and retained history.
- `docs/DOCUMENT_ANALYSIS_DIAGNOSTICS.md`: this report.

The prior local schema-width migration/model/test/doc changes were preserved. This investigation introduces no schema migration, dependency, frontend or infrastructure changes. No deployment or production retry was performed.

Validation command: `PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q` — **87 passed, 6 skipped**, with 21 dependency/lifecycle deprecation warnings. Six PostgreSQL integration cases were skipped because no explicit safe `FORMA_TEST_POSTGRESQL_URL` is configured. `git diff --check` passed. No live provider/storage/database integration was attempted.
