# Forma — creative redesign and production bug fixes

Implemented locally on 2026-10-15. The current pass redesigns the visuals while preserving the earlier product fixes. No deployment, paid inference, real decision edits, grade publication or production configuration changes were performed. Development reused the saved synthetic review copy, with the document worker and paid AI disabled.

## Current direction — «Бюро мысли»

The second creative pass replaces the paper/forest/serif direction with an experimental academic print studio. Ultramarine ink, citron, lilac working surfaces, near-black navigation and pink annotations form one identity. Locally served Unbounded supplies wide Cyrillic display typography; IBM Plex Sans and Mono retain readable academic text and precise metadata. The four-part registration mark, cut-corner optical print, catalogue indexes and annotated specimen connect the public site to the actual application.

This is a new homepage composition, mark, artwork, type system and palette. Teacher and student course tables become indexed course covers without losing their facts or links. Teacher courses precede the review queue. Sign-in uses an asymmetric blue optical poster beside a clean form. Shared navigation, account flows, assignment tools, uploads, templates, results, originality tools, notices, empty states and the review workspace inherit the same visual system. The stylesheet is readable and organized by surface; it replaces the earlier minified identity layer.

The homepage remains `/`, the authenticated legacy list `/assignments`, teacher `/teacher` and student `/student`. Backend authorization and existing route boundaries remain authoritative. No assessment behavior, inference integration, grade publication rule or production configuration changed in this visual pass.

## Motion and interactions

- A deterministic vector optical sculpture uses 46 nested three-lobed contours. Three perspective buttons change its geometry, and a pause button controls the slow rotation. This is labelled as graphic experimentation, not AI analysis. Paths are memoized; there is no continuous JavaScript rendering loop, WebGL, animation library or remote artwork request.
- Rotation pauses outside the viewport, on hidden tabs, when explicitly paused, and on all entry forms. Observers and listeners clean up on unmount. Reduced-motion preferences disable rotation, loading effects, transitions and smooth scrolling.
- The synthetic walkthrough changes its explanation, specimen note and status together. Native FAQ disclosures, anchors, keyboard focus, distinct selected states and tactile CTA feedback remain functional.
- The review retains original/criteria tabs, private page navigation, independent criterion expansion, evidence links, explicit teacher score inputs, drafts and separate confirmation/publication actions. Decorative navigation indexes are hidden from assistive technology.
- Main authored contrast pairs: body 13.61:1, secondary text 5.51:1, white/ultramarine 8.51:1, ultramarine/citron 7.52:1. Forms retain visible labels and focus outlines. The phone document toolbar wraps into two rows and primary touch controls are at least 44 pixels tall.

## Seven reported bugs

| Issue | Cause and implementation |
| --- | --- |
| Student UUID instead of name | `_student_identity` returned the ID twice. New academic records now use the authenticated account's display name. Already-authorized submission lists, review details, teacher queue and roster resolve historical UUID values on read. Unknown identities get a short readable fallback. Legacy anonymous identifier/name fields keep pseudonyms; existing records are not rewritten. |
| Impossible `2 / 1` review counter | `_assignment_json` counted answers while its denominator counted submissions. It now groups by submission and counts each submission once, only after every expected question has an explicit teacher score and reviewed/approved state. Zero counts as a score; AI proposals, incomplete work and reopened answers do not count. Academic drafts and publication remain separate records; the teacher queue still lists submissions without a published grade. |
| Internal state names | `lib/presentation.ts` supplies Russian status labels and a safe unknown-state label. Assignment, submission, enrollment, material, queue and diagnostic views use product labels instead of raw enums. API state values remain stable. |
| Infrastructure exposed to students | The student progress API now returns only ID, status and a product explanation, withholding provider/model/billing diagnostics and operational error bodies. Teachers retain the full existing diagnostic response. The student UI no longer displays backend error text or worker notes; request errors are translated at the shared presentation boundary. |
| Forbidden upload still selectable | Shared submission availability covers opening time, deadline, explicit closure and resubmission policy. `SubmissionGate` removes prohibited inputs and buttons from the DOM, including keyboard/file-drop targets. The submit handler also checks eligibility. Existing backend enforcement is retained. |
| Misleading breadcrumb | The student assignment page fetches its authorized course with the student role. The course crumb displays the actual course code/name and links to that course; the last crumb displays the assignment. Loading state uses a neutral course label. |
| Inconsistent terminology | Product role labels use «Студент» and «Преподаватель». Default question/rubric placeholders, entry flows, success/error messages and semester labels are localized. Teacher-authored instructions, saved model responses, original quotations and historical anonymous IDs retain their source language. Translated generic rubric defaults remain ineligible for AI scoring until clarified and approved. |

Core implementation: `backend/student_identity.py`, `backend/student_messages.py`, `academic_api.py`, `assignment_api.py`, `document_review.py`, `analysis_api.py`, `courses.py`; `frontend/src/lib/presentation.ts`, `components/submission-gate.tsx`, `components/form-study.tsx`, `components/forma-mark.tsx`, `app/identity.css`, shared shells and route views.

## Current verification and captures

The current visual pass uses the saved synthetic `.local/redesign-review` copy. `run_local_qwen.py --review-only` disables workers and paid requests and points unused local inference to loopback port 9. No inference, real grading edits, publication or production access is needed. No dependency or migration was added. Unbounded WOFF2 subsets and their SIL OFL license are stored locally; fonts never require runtime Google Fonts access.

- **26 frontend tests pass**: route boundaries, same-origin authentication proxy, private PDF access, upload eligibility, explicit teacher scores, drafts and publication readiness.
- **79 release backend tests pass**, with 21 existing dependency/lifecycle warnings: product identity/diagnostics safeguards, persistence, student PDF workflow, accounts/courses, review drafts/publication/authorization, assessment, mocked OpenRouter and institutional roles. Tests use mocks or synthetic fixtures.
- TypeScript, the Next production build, the OpenNext Cloudflare Worker bundle and `git diff --check` pass. The Worker was built locally; no upload or deployment command ran.

Actual local Chrome captures (Safari for sign-in), cropped to the application frame and scaled to the labelled CSS viewport size:

- [Homepage — 1440 × 900](../artifacts/bureau-redesign/home-desktop.png)
- [Homepage — 390 × 900](../artifacts/bureau-redesign/home-mobile.png)
- [Method — desktop](../artifacts/bureau-redesign/method-desktop.png)
- [Method — phone](../artifacts/bureau-redesign/method-mobile.png)
- [Sign-in — desktop](../artifacts/bureau-redesign/login-desktop.png)
- [Teacher course catalogue — desktop](../artifacts/bureau-redesign/teacher-desktop.png)
- [Saved review — desktop](../artifacts/bureau-redesign/review-desktop.png)
- [Saved review, original tab — phone](../artifacts/bureau-redesign/review-mobile.png)
- [Saved review, criteria tab — phone](../artifacts/bureau-redesign/review-criteria-mobile.png)

These are native browser screenshots of the implementation, not generated mockups. The exact-width `/design-preview?width=1440&path=/` development aid displays real same-origin routes; widths 768 and 390 are available too. It preserves authentication and returns 404 in production. No changes to real academic records are required for visual inspection. Checked the desktop and phone homepage, optical perspective/pause controls, synthetic walkthrough, course catalogue, private original, phone original/criteria tabs, criterion expansion, blank teacher score state and disabled publication. The evidence action returned to the Original tab with page 2 selected and its private image loaded. The sign-in layout was inspected in Safari. A reliable final tablet capture and full repeat of every route were not obtained after the native capture surface began returning missing-window errors. This pass is not a physical-device, complete screen-reader or cross-browser certification.

Both local preview servers and the build process were stopped after verification to release RAM and CPU; ports 3008 and 8012 have no listeners. The temporary Chrome and Safari preview tabs were closed. User-owned browser processes were not terminated.

The earlier `artifacts/creative-redesign` screenshots are historical and show the superseded visual direction. The seven fixes above and their broader 79-test backend verification belong to that earlier implementation; they were preserved, not reimplemented during the current pass.

```sh
PYTHONPATH=backend FORMA_AI_PAID_ENABLED=false backend/.venv/bin/python -m pytest backend/tests/test_product_quality.py backend/tests/test_review_workspace.py backend/tests/test_accounts_courses.py -q
npm --prefix frontend test
frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json
# From frontend/, build only; never uploads or deploys:
node_modules/.bin/opennextjs-cloudflare build
git diff --check
```

## Safe deployment procedure — approval required, not executed

1. Review this diff, commit the complete backend/frontend/assets/tests change on a review branch and record the candidate SHA and currently deployed Render/Cloudflare revisions. Check that no ignored runtime files, credentials, private documents or benchmark databases enter the commit. Do not push to an automatically deployed production branch during preparation.
2. Use isolated staging services and a synthetic dataset. Keep `FORMA_AI_PAID_ENABLED=false`; preserve the existing monthly/job/concurrency safeguards. This change needs **no new migration, environment variable, provider configuration, bucket or DNS change**. Existing staging authentication, database, private storage and same-origin frontend proxy must be configured separately from production.
3. Deploy the candidate backend on staging first, then its frontend Worker. Verify student/teacher isolation, historical names, complete-submission counters, student-safe progress, prohibited re-upload, course breadcrumbs, private originals, persisted drafts and manual score inputs. Repeat 1440/768/390 layouts, reduced motion, keyboard navigation, dialogs and logout. Confirm `/design-preview` and the existing review-preview route return 404 in a production build. No inference or grade publication is needed for these checks.
4. Re-run the commands above on the exact candidate revision. Back up production according to the existing operational procedure and confirm that the previous backend/Worker revisions are available for rollback. Obtain explicit production deployment approval with those SHAs and staging results.
5. **Only after approval:** use Render's existing `forma-api` manual deployment for the reviewed backend commit. Wait for `/api/health` and read-only authenticated checks. Keep its Neon/R2/auth/provider settings unchanged. Deploy the matching frontend using the existing script from the repository root: `npm --prefix frontend run cf:deploy`. This targets `forma-frontend` in the existing Wrangler configuration; do not change bindings, domains or secrets. Confirm the intended Cloudflare account/project before invoking it.
6. Check public `/`, teacher/student login routing, `/assignments`, read-only academic navigation and access denials. Use synthetic staging records for any mutation test. Keep paid AI disabled and do not publish real grades as a deployment check.
7. If rollback is required, restore the recorded previous Cloudflare Worker version and Render backend revision through their deployment histories. Do not restore an old database over newer student work, drop tables, erase drafts or reset the AI ledger. No reverse migration is necessary. The current API state enums and existing academic record IDs are preserved.
