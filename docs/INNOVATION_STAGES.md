# Forma innovation stages

Scope agreed on 2026-10-16: all 18 ideas from `Forma_Product_Innovation_2026-10-16.md`, delivered in stages. This file records implemented behavior separately from planned extensions. Stage 1 is implemented locally; stages 2–5 remain work to do. No stage has been deployed by this task.

## Delivery map

| Report idea | Current implementation | Remaining delivery |
| --- | --- | --- |
| 1. Confirmed decision cards | Stage 1: immutable cards from saved, confirmed teacher criteria; source review, rubric signature, original score and teacher observation retained. Applying requires a new observation on an existing page and copies explanation/provenance, never points or acceptance. | Coordinate selection/highlighting is outside the page-anchor baseline. |
| 2. One question across the group | Stage 1: latest-attempt queue, explicit question-to-PDF-page mapping, question focus, previous/next links and return to all criteria. Saves still cover the complete rubric. | Grouped simultaneous document comparison can follow pilot feedback. |
| 3. Assignment preflight | Stage 1: date and score checks, rubric-total warnings and an expandable student preview in the existing creation form. | Semantic contradictions in prose remain a teacher check. |
| 4. Reference examples and calibration | Stage 1 baseline: confirmed cards can be marked as reference examples and opened alongside the current original. | Stage 4: independent reviewer samples and criterion-level disagreement discussion. |
| 5. Rule-change impact preview | Not implemented. Existing review history and new card-use links are prerequisites. | Stage 2: versioned rule proposals, affected draft/confirmed/published counts, explicit diff and review links; no automatic regrading. |
| 6. Error-carried-forward reasoning | Not implemented. | Stage 2: teacher-authored step dependencies, explicit partial-credit policy and reminders; no automatic inference of reasoning or points. |
| 7. Submission completeness | Stage 1 baseline: readable/complete self-checks, visible receipt ID, serialized upload button and retry key deduplication. An accepted receipt survives a subsequent status-refresh error. | Stage 3: assignment-specific required parts, bounded multiple attachments and a teacher triage queue. A self-check does not prove semantic completeness. |
| 8. Criterion-specific clarification | Not implemented. | Stage 3: student-owned thread pinned to a published review/criterion, teacher reply and resolution history; no grade change implied. |
| 9. Revision response | Existing immutable attempts; no linked response implementation. | Stage 3: structured response to a frozen published comment, old/new anchors and teacher disposition under existing resubmission policy. |
| 10. Next-class summary | Existing confirmed assessment insights; no new cohort action summary. | Stage 2: confirmed card-use frequencies with explicit denominators, private source links and teacher-selected follow-up material. |
| 11. Similarity context | Existing saved comparison reports and explicit analysis states; no new exclusion rules. | Stage 3: exact, bounded assignment-context exclusions with version, reason and original/excluded evidence; verify real pipeline with synthetic pairs. |
| 12. Dispute dossier | Existing teacher notes and saved comparison evidence; no dossier export. | Stage 3 after 11: immutable private evidence package, scope, exclusions, alternative explanation and human conclusion. |
| 13. Unusual shared errors | Not implemented. | Stage 5: bounded, manually labelled pattern search with observed frequency and source context; no probability of misconduct or automated accusation. |
| 14. Lab data/report cross-check | Not implemented. | Stage 5: safe CSV attachment/parser, explicit columns/units, one bounded fit model, rounding tolerance and reproducible receipt; never execute uploaded code. |
| 15. Claims/evidence map | Not implemented. | Stage 5: a bounded manual map with student claims, private anchors and teacher observations; no claim to verify scientific truth. |
| 16. Alternative symbolic answers | Not implemented. | Stage 5: restricted structured grammar, explicit domain/assumptions and resource limits; return “not verified” outside supported scope. Numerical samples alone cannot establish equivalence. |
| 17. Small reviewer team | Existing ownership/institution authorization and publication conflict detection; no TA claims or independent review flow. | Stage 4: explicit course delegation, claim expiry/conflict handling, independent draft decisions, professor resolution and calibration from 4. |
| 18. Portable course review package | Stage 1 baseline: authenticated CSV of published grades, frozen feedback and stable student/submission/review IDs. Drafts are excluded; zero scores are retained. Existing assignment reuse remains available. | Stage 4: previewed roster/work mapping, confirmed import, individual feedback packages and versioned course-template transfer. No silent student matching. |

## Stage boundaries and acceptance checks

1. **Teacher-memory pilot — implemented.** Cards/reference examples, question queue and page mapping, deterministic preflight, submission self-check/receipt retry, published-grade CSV. Exercise manual and mocked assisted review; prove that reuse assigns no score, publication stays deliberate, private card source metadata does not reach student feedback, and concurrent upload retries do not create duplicate jobs/attempts.
2. **Consistent rules and teaching actions — pending.** Ideas 5, 6 and 10. Preserve original decisions, separate proposed changes from applied decisions, count only comparable confirmed reviews, and keep published grades fixed until explicit publication.
3. **Student follow-up and integrity context — pending.** Ideas 8, 9, 11 and 12 plus the remaining part of 7. Pin discussion/revision to immutable versions; test student isolation, closed deadlines, attachment limits, exact exclusions and private export.
4. **Reviewer teams and portability — pending.** Idea 17, calibration from 4 and the rest of 18. Introduce delegation deliberately, verify independent samples and stale-write conflicts, and preview every identity mapping before import.
5. **Bounded subject tools — pending.** Ideas 13–16. Ship them individually with strict scope and resource limits, synthetic reference fixtures and explicit unsupported outcomes. These are separate experiments, not a universal handwritten reasoning engine.

The existing visual identity, provider/budget controls and manual publication remain in place. No stage requires paid inference for its initial manual/deterministic version. No quality or time-saving claim has been established by a real course pilot.

## Stage 1 use

From an assignment's submissions list, open **Проверять по вопросам**. The queue uses only each student's latest immutable attempt. Without a teacher mapping it says that mapping is needed; it never invents page locations. In the review workspace, **Страницы вопросов · ручная разметка** loads/saves page sets separately, with stale-write detection. Unsaved mappings block question selection/reload until saved or explicitly reset and participate in the workspace navigation warning.

The queue now offers **Разметить страницы** directly for PDF submissions with available pages and a missing/stale mapping. This link selects the question, opens the mapper above the other review tools, loads saved page metadata, and focuses the mapper. On narrow screens it opens **Критерии** automatically. Ready mappings retain their ordinary review links; non-PDF or unavailable pages do not offer an unusable mapping action. The history disclosure is labelled **Подтверждённые наблюдения о студенте в курсе** to match its student-specific scope.

In **Память решений и примеры-ориентиры**, explicitly load cards for a criterion. Only cards from the same course and matching question/category/criterion signature are compatible. Assisted review uses the approved assessment rubric signature. A new page and teacher observation are required to reuse a card. The source score is an example, not a suggested input value. Save/confirm the resulting review through the existing actions; publication remains another explicit step.

Card creation uses the selected criterion in the latest saved review. A draft or a criterion without points cannot become a confirmed reference. Cards and page maps are append-only. Rubric changes hide incompatible cards and mark old page maps stale. Page observations are teacher assertions, not machine-verified quotations or highlight coordinates. This first card/mapping implementation requires a PDF with stored page structure.

Students explicitly check readability and required parts before uploading. This does not certify document content. A request UUID remains stable for retries of the selected file while the page is open. Server deduplication is scoped to assignment/student/request UUID and checks both content hash and filename, atomically with the attempt/job. A changed file requires a new key. An accepted retry can retrieve its receipt after a deadline; current enrollment authorization still applies. Reloading the page does not preserve an uncertain client retry key.

The published-grade CSV has one row per published submission, including stable IDs and frozen feedback. Multiple published attempts can therefore produce multiple rows; it is not an automatically collapsed LMS final-grade roster. Empty assignments return the header. Text cells are protected against spreadsheet formula injection.

## Files and integration

| Files | Responsibility |
| --- | --- |
| `backend/review_pilot_models.py`, `backend/review_pilot_contracts.py`, `backend/review_pilot.py` | Immutable records, strict anchors/contracts, course authorization, cards, page mapping, queue and CSV |
| `backend/document_review.py`, `backend/assessment_api.py` | Validate/persist card provenance for manual/assisted saves; omit internal card-use data from student feedback |
| `backend/academic_api.py` | Atomic upload receipt deduplication under the existing assignment lock |
| `backend/migrations/__init__.py`, `backend/persistence.py`, `backend/main.py`, `backend/permissions.py` | Additive schema and authenticated router integration |
| `frontend/src/lib/review-pilot.ts`, `frontend/src/lib/review-workspace.ts`, `frontend/src/lib/assignment-preflight.ts` | Typed payloads, provenance persistence, queue URLs and deterministic checks |
| `frontend/src/components/review/decision-memory.tsx`, `frontend/src/components/review/question-review-tools.tsx`, `frontend/src/components/review/teacher-review-workspace.tsx` | Existing-style teacher controls, saved review integration and unsaved mapping protection |
| `frontend/src/app/teacher/assignments/[assignmentId]/question-review/page.tsx`, `frontend/src/app/teacher/assignments/[assignmentId]/submissions/page.tsx` | Queue, entry point and private CSV download |
| `frontend/src/components/assignment-create-form.tsx` | Preflight and student preview |
| `frontend/src/app/student/assignments/[assignmentId]/page.tsx`, `frontend/src/lib/academic.ts` | Self-checks, stable retry key and receipt UI |
| `frontend/src/app/identity.css`, `frontend/src/lib/presentation.ts` | Scoped responsive controls and translated API errors |
| `backend/tests/test_review_pilot.py`, `frontend/tests/review-pilot.test.cjs` | Permissions, immutability, boundaries, races, privacy, retry and editor regressions |

## Verification and rollout

Synthetic fixtures and mocked AI only. Full backend run: **229 passed, 1 skipped**, including PostgreSQL race tests in a disposable loopback-only database. The skipped test requires live Gemini. After the last privacy assertion, the focused pilot rerun passed **11 tests**, with its opt-in PostgreSQL test skipped while that server was stopped. Existing dependency/lifecycle deprecation warnings remain.

Frontend: **62 tests passed**; TypeScript checking, the final Cloudflare OpenNext build and `git diff --check` passed. The relevant checks are:

```sh
# Point this variable only at a disposable local PostgreSQL server.
FORMA_TEST_POSTGRESQL_URL=postgresql://127.0.0.1:55473/postgres PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend test
frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json
# Run in frontend; this builds only, without upload/deployment.
npx --no-install opennextjs-cloudflare build
git diff --check
```

Local Chrome inspection covered the desktop workspace and a 390-pixel authenticated frame, compatible reference loading, fresh evidence, preservation of an existing score while applying a source card with a different score, draft save, page-2 navigation and mapping save. Later Chrome capture returned blank content; the final mapping warning, standalone queue appearance, student upload form and assignment preflight have automated coverage but were not all visually rechecked. This is not physical-device, cross-browser or full screen-reader certification. No production workflow or live cloud inference was exercised.

Deploy only after separate approval. Back up the target database and deploy the backend before the frontend. Startup applies additive migration **012_review_pilot**, creating `review_decision_cards`, `review_question_page_maps` and `submission_upload_receipts`; there are no new environment variables, dependencies or backfills. Existing grade and budget records are not migrated. Roll back the frontend first, then the backend if needed, retaining the additive tables and immutable records. Do not drop them as an application rollback step.

Temporary backend/frontend preview servers and the disposable PostgreSQL instance were stopped; the task-created local browser tab was closed. Existing user services and tabs were left running.

Queue-discoverability follow-up on 2026-10-16: **65 frontend tests passed**, TypeScript checking and the Cloudflare build passed. New regressions cover missing/stale/ready mappings, unavailable/non-PDF originals, direct entry into the second question, metadata-only loading, tool focus and the student-scoped history label. Local Chrome inspection covered the queue action and the revealed mapper on desktop and at 390 px using synthetic fixtures. No backend contract, migration or production setting changed in this follow-up.
