# Phase 4.2 — Teacher Review Workspace

The teacher review page now puts the original document beside compact, independently expandable rubric criteria. It reuses saved interpretations and assessment suggestions for problem sets, essays and laboratory reports. Opening, reviewing, saving and publishing an existing result requires no inference. This phase ran no Ollama, Gemini or OpenRouter inference, created no model benchmark, installed no dependencies and made no deployment or production changes.

## Review workflow

The overview shows the assignment, student, submission date, page count, saved suggestion availability and official grade. An ungraded submission says **Не выставлена**. Desktop content uses approximately 57% document / 43% assessment; narrower screens use **Оригинал / Критерии** tabs. The interface follows the existing Russian locale, while source quotations and saved model text retain their original language.

One document toolbar controls pages, zoom, download and fullscreen. Evidence links open the corresponding original page. The authenticated viewer caches up to five bounded page images in memory and stays mounted while scores and feedback change. Source text, LaTeX, versions, processing controls, advanced rubric editing and confirmed history remain available under progressive disclosure in **Диагностика**.

Each criterion shows its maximum, AI suggestion or absence of one, summary and saved teacher status. Expanded content separates observed evidence, AI interpretation, rationale, improvements and teacher decisions. AI scores never initialize teacher score inputs. Teachers can accept, edit, reject or defer; rejected/deferred assisted decisions carry no points. Independent manual grading remains available in the same workspace.

The bottom action bar separates **Сохранить черновик**, **Подтвердить критерии** and **Опубликовать оценку**. Drafts may be incomplete and do not become confirmed historical findings or publishable grades. Confirmation persists explicit decisions; complete accepted/scored decisions reuse the existing unpublished manual review. Publication requires another deliberate confirmation. Existing published feedback remains unchanged until publication succeeds. The client supplies the previously observed published-review ID so a concurrent publication produces a conflict instead of silently replacing it.

Failed saves retain inputs. Reload/close, internal links and logout warn about unsaved changes. Switching saved assessment versions or grading modes also asks before discarding edits. There is no autosave.

## Components and API changes

| File | Responsibility |
| --- | --- |
| `frontend/src/lib/review-workspace.ts` | Typed API normalization, criterion identity, saved editor state, score validation and publication readiness |
| `frontend/src/components/review/teacher-review-workspace.tsx` | Loading, persistence, drafts, publication and navigation guards |
| `frontend/src/components/review/submission-overview.tsx` | Submission and official grade overview |
| `frontend/src/components/review/document-viewer.tsx` | Private page viewer, navigation, zoom, cache and fullscreen |
| `frontend/src/components/assessment-panel.tsx` | Reusable `RubricReviewPanel` |
| `frontend/src/components/review/criterion-card.tsx` | `RubricCriterionCard`, `EvidenceLink`, `TeacherDecisionEditor` and bounded math rendering |
| `frontend/src/components/review/review-action-bar.tsx` | Save, confirm and explicit publication actions |
| `frontend/src/components/review/assessment-diagnostics.tsx` | Secondary history, rubric settings, extraction and existing analysis controls |
| `frontend/src/app/teacher/submissions/[submissionId]/review/page.tsx`, `frontend/src/components/app-shell.tsx`, `frontend/src/app/globals.css` | Route integration, restrained responsive layout and focus/touch styles |
| `backend/document_review.py` | Optional incomplete manual drafts, overview metadata, private page rendering and publication conflict check |
| `backend/assessment_api.py` | Optional decision drafts and overall feedback using existing immutable records |
| `backend/scripts/prepare_review_workspace.py`, `backend/scripts/run_local_qwen.py` | Saved-data copy and inference-disabled local launch |
| `frontend/src/components/review/review-viewport-preview.tsx`, `frontend/src/app/teacher/review-preview/[submissionId]/page.tsx` | Development-only authenticated viewport preview |
| `backend/tests/test_review_workspace.py`, `frontend/tests/review-workspace.test.cjs` | Draft, score, publication, authorization and view-model regressions |

The existing review GET adds assignment category/instructions, submission date and published review identity. A teacher-only `GET /api/document-review/{submission_id}/pages/{page_number}` renders a PDF page as a private/no-store PNG, capped at a 1600-pixel longest edge and the existing 30 MB / 50-page document limits. It uses existing PyMuPDF, storage and course authorization; no public document URL or new rendering service is introduced.

Existing save endpoints accept an optional `draft` flag, defaulting to the prior confirmed behavior. Draft status is stored in existing JSON records; there is **no migration**. Draft assessment decisions do not supersede confirmed history. Publish accepts an optional `expected_published_review_id` for conflict detection under the existing submission lock. Incomplete/unconfirmed manual drafts cannot publish. Existing interpretation, provider, worker, budget and publication authorization mechanisms are retained.

## Launch with existing saved data

Run from the repository root with the existing virtual environment and frontend dependencies. The preparation script requires this workspace's saved synthetic `artifacts/assessment-phase-4/run-03` database, storage and runtime configuration. It copies them; it does not rerun that benchmark. Choose a **new** output directory:

```sh
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/prepare_review_workspace.py --output .local/review-workspace-new
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/run_local_qwen.py --runtime-file .local/review-workspace-new/runtime.env --review-only
```

In a second terminal, from the repository root:

```sh
FORMA_BACKEND_URL=http://127.0.0.1:8000 npm --prefix frontend run dev -- --hostname 127.0.0.1
```

Open `http://localhost:3000/login` using **localhost** in the browser for the existing same-origin cookie proxy. Sign in with synthetic teacher `local-teacher@example.test`, password `Forma-local-benchmark-only-123`. Read the review URL from `.local/review-workspace-new/review-fixture.json`. Existing saved math, essay and lab examples are listed there too.

The copy includes one clearly labelled deterministic three-page UI fixture assembled from existing synthetic PDFs, with three criteria, an abstention and evidence on pages 1–3. Its suggestions are UI fixture data, not new model results. The original saved benchmark data remains untouched. Runtime credentials, database and private objects stay ignored. `--review-only` disables background document work, keeps paid calls disabled and directs new local inference requests to unused loopback port 9. No model needs to be loaded. Existing explicit inference controls remain secondary; they were not invoked during this phase.

The already prepared local copy is `.local/review-workspace-phase42`. Its review route is `/teacher/submissions/db39f25a-f523-4664-afde-6d89af3cd771/review`; use its matching runtime file when launching that copy. Temporary verification servers were stopped after checks.

## Visual review and verification

After login, open `/teacher/review-preview/<submission-id>` on the local development server. Choose **1440 × 900** or **390 × 900** to render the real authenticated review route in an exact-width frame. This is a development-only viewport aid, not a mock API or authentication bypass; it returns 404 in a production build. Capture the frame or use the browser's responsive tools for additional sizes.

Both widths were inspected in local Safari and screenshots were captured through the computer-use surface. Reproducible instructions are provided here rather than exported screenshot files. The desktop document/criteria balance, phone tabs, wrapping controls, private original, page-2 evidence navigation, fullscreen/Escape, blank teacher score after Accept, draft save and persisted score/feedback after reload were checked. The copy's official grade remained ungraded; no UI publication was performed. API tests cover explicit publication separately.

Checks run on 2026-10-15, using mocks or saved/deterministic data only:

- Relevant backend regression suite: **48 passed**, with 21 existing dependency/lifecycle deprecation warnings. This covers assessment, student workflow, accounts, local provider contracts and the new workspace API tests.
- Final focused draft/publication rerun: **4 passed**, including publication conflict detection.
- Frontend: **21 tests passed**; TypeScript checking and Next production build passed.
- `git diff --check` passed.

Commands:

```sh
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/test_review_workspace.py backend/tests/test_assessment.py backend/tests/test_student_pdf_workflow.py backend/tests/test_accounts_courses.py backend/tests/test_ai_providers.py -q
npm --prefix frontend test
frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json
npm --prefix frontend run build
git diff --check
```

## Remaining UX limits

- The page viewer uses bounded raster images: no text selection/search, annotations or vector-quality enlargement. Original download remains available. Evidence jumps to a page, without inventing highlight coordinates.
- Non-PDF submissions offer private download, extracted-text diagnostics and manual review; this phase adds no Word/slide renderer or assessment strategy.
- Unsaved-change protection covers reload/close and app link/logout/version/mode actions. Browser Back/Forward during client-side navigation is not fully guarded; save before using it.
- The visual pass used desktop Safari and exact-width frames. It is not a physical mobile-device, complete screen-reader or cross-browser regression pass. Reject/defer and publication semantics have automated coverage, but every interaction was not repeated manually at both widths.
- Scores require explicit saving and confirmation. Concurrent publication is checked; concurrent draft edits remain immutable versions rather than collaborative live editing. Backend draft support must be present alongside the frontend change.

All earlier Phase 4 model-quality limitations still apply. This phase improves review usability using existing results and makes no new assessment-accuracy claim.
