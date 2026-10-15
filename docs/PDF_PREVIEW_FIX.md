# Authorized teacher PDF preview: confirmed 403 fix

## Root cause and exact denial

The review page called `authenticatedResourceUrl` with an already proxied URL, `/api/backend/api/submission-files/{submission_id}`. The helper unconditionally prefixed non-HTTP URLs with `/api/backend` again.

The actual request chain before this fix was:

```text
Browser:  /api/backend/api/backend/api/submission-files/{id}
Proxy:    path = [api, backend, api, submission-files, {id}]
Render:   /api/backend/api/submission-files/{id}
```

`permissions.authorize_request()` rejects that malformed Render route at its final default branch: HTTP 403, `This route has no access policy.` The request never reaches `document_review.original_file()` or private R2 retrieval. This explains why the authorized review/text endpoint works while PDF fetch fails. The UI turns this response into `Не удалось загрузить файл (403).`

This is reproduced locally: the added frontend test failed with that exact UI error before the fix. A backend regression confirms the malformed URL hits the specified 403 branch even with the authorized course teacher's real account session. Production network/log inspection was not performed; the diagnosis is confirmed against the repository's actual caller, helper, proxy and access policy.

## Fix and security trace

The review page now passes the backend-relative `/api/submission-files/{id}` path. The shared helper accepts either backend-relative or already proxied paths and prefixes once, preserving existing resource callers. The correct browser URL is `/api/backend/api/submission-files/{id}`, forwarded to Render as `/api/submission-files/{id}`.

`authenticatedFetch` retains `credentials: same-origin`. The Cloudflare proxy reads the HttpOnly `forma_session` cookie and supplies its bearer token to Render. The preview requires no JS-readable session token. Legacy bearer-session compatibility remains intact. GET requests retain their existing policy; mutation origin checks and `redirect: manual` are unchanged.

The proper backend route delegates to `get_submission`, `materials.access` and `require_teacher`/`require_student`. Teacher access still checks course ownership plus active institutional teaching membership (or the existing authorized admin policy). An unrelated teacher is denied. An enrolled student can retrieve only their own submission; same-course enrollment alone does not authorize a peer's private file. Revoking the teacher's institutional membership removes access even while an existing account session remains valid.

Only after those checks does `read_blob` call private R2 `get_object`, read its stream and close it. The endpoint returns `application/pdf`, private/no-store and nosniff headers. The proxy forwards the PDF body/MIME type with no-store caching. The helper creates a local Blob URL used by the existing embedded viewer; no R2 key, signed URL, public bucket or query-string credential is exposed. The previous attachment response header does not force a download here because the viewer uses fetched Blob bytes.

No backend authorization/storage code, schema, job data or production settings were changed for this fix. Existing diagnostics, pending schema-width changes and student-first workflow were preserved.

## Changed files

- `frontend/src/lib/api.ts`: prevent duplicate proxy prefix in resource fetches.
- `frontend/src/app/teacher/submissions/[submissionId]/review/page.tsx`: use backend-relative PDF path.
- `frontend/tests/proxy.test.cjs`: exercise actual resource helper through actual proxy handler with cookie-only session and PDF bytes, and preserve backend 403 denials.
- `backend/tests/test_private_pdf_preview.py`: real verified account sessions, course ownership/institutional membership and peer enrollment; reproduce malformed-route denial; allow authorized teacher/own student; deny unrelated teacher/enrolled peer/revoked teacher before storage reads. Private R2 transport is mocked; stream read/close is exercised.
- `docs/PDF_PREVIEW_FIX.md`: this report.

## Verification limits

Tests exercise the real Next proxy handler under Node with an upstream HTTP fixture, and the real backend auth/access/storage path under isolated SQLite with mocked R2. They do not run a live Cloudflare Worker, Neon or R2 bucket, or visually inspect the browser-native PDF plugin. After a separately approved frontend release, verify the browser Network panel has one `/api/backend` prefix, the PDF GET returns 200/application/pdf and page/zoom navigation displays the original. No deployment, production request or data modification was performed during this fix.

Validation: `PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q` — **88 passed, 6 skipped**, with 21 dependency/lifecycle deprecation warnings. PostgreSQL-only cases are skipped because a safe test URL is not configured. `npm test` in `frontend` — **10 passed**. `npx tsc --noEmit`, `npm run build`, `npx opennextjs-cloudflare build` and `git diff --check` passed. Builds generated local artifacts only; no Worker was published.
