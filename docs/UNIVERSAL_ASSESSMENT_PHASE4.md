# Phase 4 — rubric-driven assessment, first local milestone

Historical Phase 4 report: the later [Cloud Qwen Pilot](CLOUD_QWEN_PILOT.md) adds explicitly configured, budgeted OpenRouter assessment. Ollama remains the default. The local-only statements below describe this original milestone.


The subsequent [Phase 4.2 Teacher Review Workspace](TEACHER_REVIEW_WORKSPACE.md) redesigns the review interface using these saved results. Its guide supersedes the UI layout description below; the original evaluation evidence remains unchanged.

Implemented for **problem sets, essays and laboratory reports**, using one evidence/criterion contract and one explicit teacher-decision workflow. Assessment is separate from document understanding. It uses **only local `qwen3-vl:8b-instruct`**, even if the deployment default is Gemini or OpenRouter. There is no assessment cloud fallback, paid call, code execution, source retrieval, training, grade creation or automatic publication. Existing providers, budget accounting, institutional access checks, originals, corrections and grades remain available.

## Architecture and workflow

1. Create a normal assignment with full instructions, category and explicit criteria/point limits. No answer key or template PDF is required. The existing creation screen supplies criterion names and maxima; the review screen adds full performance descriptions, feedback requirements, reference material, optional advisory weights and historical tags.
2. Upload a PDF through the existing student-first private submission flow. Existing document understanding produces immutable sections with observed transcription, page associations and separate model interpretations. Teachers can correct those observations before evaluation.
3. In teacher review, expand **Требования задания**, clarify the complete instructions and criterion descriptions, then explicitly approve the rubric. Generic auto-created “Overall correctness” criteria are refused. Existing question statements and reference answers initialize the editor without truncation; long contexts are refused before inference instead of silently dropping instructions. A rubric version must retain all existing criterion IDs and point maxima. Point allocations are the scoring weights; the optional `weight` field is advisory emphasis and does not multiply scores.
4. Optionally request local AI-drafted performance descriptions. This is an explicit, bounded local call with a 45-second timeout and a three-request rate limit. Its result is an unapproved candidate. It cannot change criterion IDs, maxima, weights, tags or the full task/reference material. It never becomes a scoring rubric until a teacher approves it. Manual rubric editing remains available on errors or model unavailability.
5. Explicitly request assessment. The API snapshots the approved rubric, assignment title, immutable interpretation/correction IDs, original content hash, observed sections and source limitations into a normal leased `ProcessingJob`. Local model configuration and `rubric-eval-v3` participate in job identity. Existing attempts, owner/expiry fencing, job quotas and retries are reused. Assessment does not use the interpretation cache or create a misleading new interpretation version.
6. The assessment service applies category-specific reasoning guidance from a strategy registry. A provider-independent Pydantic contract validates criterion coverage, finite scores within approved maxima, evidence section/page identity and source quotations. It cannot mark its own findings verified or teacher-confirmed. No source material or external computation is independently verified by this implementation.
7. Teachers explicitly accept, edit, reject or defer each criterion. Every decision creates another immutable review version, including teacher feedback and score overrides. Rejected/deferred items cannot carry points. If every criterion is explicitly accepted and scored, the API creates an **unpublished existing `DocumentReview`**, with the approved criterion wording snapshotted. Existing manual grading remains available independently. Only the existing, separate teacher publication action can create/publish an academic grade.

The assessment contract records criterion identity, optional proposed score, rationale, exact observed evidence, separate AI interpretation, strength/concern/mixed/insufficient-evidence classification, improvement, missing source evidence, uncertainty and `needs_review`. Evidence sufficiency and verification are separate concepts. An incorrect observed step is evidence of a concern; missing performance elements should not be confused with missing source pages. Qwen still sometimes confuses these concepts; the examples below document that limitation.

Evidence never quotes model interpretation as observed text. Exact quotations are preferred. PDF line wraps can differ from the model's quote: only whitespace equivalence with **one unique matching source span** is allowed, and the exact original span is persisted. Words and punctuation are never fuzzy-matched or repaired. Malformed JSON, invented passages/IDs/pages, scores above rubric limits, contradictory insufficient-evidence scores and unsupported verification statuses fail validation. These checks establish structural grounding, not that an AI's reasoning about the quotation is correct.

Partial page coverage and source/hash mismatches block assessment. The original PDF and prior results remain available for manual review. A short, bounded source is required: the assessment request, system prompt and schema together must fit 18,000 UTF-8 bytes; output uses the existing local token ceiling (default 2,200), 8,192-token context, one loaded local model and one inference lock. Up to 12 criteria are accepted, but a large rubric may exceed that context/output budget and require manual review. The upstream document engine's existing page/image/time caps still apply. No unbounded whole-document evaluation is claimed.

## Teacher interface and confirmed history

The existing PDF preview/page/zoom controls remain on the left at desktop widths, with a sticky original; narrower windows stack the preview and assessment. The right side presents assignment requirements, criteria, source-linked quotations, strengths/concerns, rationale, improvements and teacher decisions. Raw transcription, LaTeX, model interpretation, corrections and analysis controls remain inside **Диагностика**. Manual scores and explicit publication remain below. Same-origin, HttpOnly-cookie proxy behavior is preserved.

Rubric tags are teacher-defined comparison identifiers, unique within a rubric. Historical insights join immutable accepted decisions to their submission, student, assignment, course, criterion and original evidence. They count distinct reviewed submissions for the same category/tag within the same course and student; the latest decision supersedes earlier reviews, including a later rejection/defer. AI-only, rejected and deferred findings do not contribute. The denominator is submissions with an accepted decision for that tag, not all submissions or all students. Concern/mixed counts have evidence links and do not establish student traits. Empty tags produce no aggregate. Comparing tags across different rubrics depends on teachers using the same meaning; this system does not infer equivalence. No training or fine-tuning occurs.

All rubric, assessment, decision and insight handlers require teaching access to the relevant course. Students and unrelated teachers cannot read draft suggestions, other students' histories or teacher-only rubric data. Confirmed feedback becomes student-visible through the existing publication flow.

## Persistence and additive migration

Existing `AcademicAssignment.questions` remains the base point allocation; `DocumentInterpretation` and `InterpretationCorrection` remain the source records; `ProcessingJob` remains the durable worker; `DocumentReview` and `AcademicGrade` retain review/publication behavior.

Migration **009_rubric_assessment** adds only:

- `assessment_rubrics`: approved instruction/rubric versions and approver.
- `assessment_suggestions`: immutable result, durable job, rubric and source interpretation/correction references.
- `assessment_decisions`: immutable per-criterion actions, teacher overrides/feedback, reviewer and optional unpublished manual-review reference.

There is no grade rewrite, student-record migration or destructive rollback. Migration 008 and its $4 monthly / $0.02 job / one-paid-request protections are preserved. Assessments cannot select paid providers, irrespective of their configured defaults or keys. Earlier migrations are retained; migration-count regression expectations now include 009.

## Actual file support

| Format | Existing workflow | Phase 4 assessment |
| --- | --- | --- |
| PDF | Private upload, bounded PyMuPDF extraction/rendering, original browser preview, page/section references, teacher corrections | Complete local slice for the three categories above, within existing limits |
| DOCX | Safe bounded OOXML extraction of paragraphs/styles and tables, download and extracted-text review; no reliable rendered page/layout preview; paragraph/table interleaving is not fully retained | Explicitly refused; manual review remains available |
| PPTX | Safe bounded OOXML extraction of slide text/tables, download and extracted-text review; no original visual slide rendering | Explicitly refused; presentation strategy is not enabled |
| Images | No complete standalone image-submission assessment path; legacy crop grading is separate | Unsupported; images embedded in PDFs use the PDF understanding path |
| Code / ZIP | Existing programming-only bounded UTF-8/static archive extraction and manual review; no code execution or trusted test runner | Explicitly refused; programming strategy is not enabled |

Existing macro/entity/embedded-executable/archive limits are unchanged. No converters, new dependencies, rendering services or execution engines were installed.

## Real local evaluation evidence

Run from the repository root, with the existing local model already pulled and no other local model loaded:

```sh
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/benchmark_assessment.py --output artifacts/assessment-phase-4/my-new-run
```

The script refuses an existing database, accepts no arbitrary input file, overrides inherited provider/database/storage settings before importing Forma, disables dotenv/SMTP/cloud keys/paid enablement, and creates isolated synthetic institution/accounts/course/PDFs. It exercises real login, enrollment, assignment creation without a template, private PDF upload, real document understanding, rubric approval, local assessment jobs, strict persistence and simulated explicit teacher overrides. Raw responses are saved only for these generated synthetic cases. Runtime credentials/database/object copies remain ignored. Simulated teacher actions test workflow; they are **not human endorsements of the model feedback**.

Actual final evidence: [run-03 report](../artifacts/assessment-phase-4/run-03/report.json), [raw responses](../artifacts/assessment-phase-4/run-03/raw-responses.json), with five generated PDFs in that directory. Every case analyzed its one PDF page and persisted a schema/evidence-valid draft. All five explicit simulated overrides created unpublished manual reviews; **zero academic grade rows** were created.

| Synthetic ground truth | Understanding / assessment seconds | Observed suggestion |
| --- | --- | --- |
| Correct F=ma solution, a=3 m/s² | 9.674 / 8.056 | Strength, 5/5; law, substitution and unit recognized |
| Incorrect a=F×m=12 m/s² | 9.353 / 10.542 | Concern; identifies multiplication instead of division and gives 3 m/s²; no proposed partial-credit score |
| Essay with thesis, two reasons, counterargument and conclusion | 10.089 / 11.161 | Strength, 5/5; identifies the requested structure without inventing a citation requirement |
| Circular, poorly supported essay | 6.152 / 11.489 | Describes weak support and missing argumentative structure, but labels it insufficient evidence and withholds a score; also overstates absence of a thesis despite an expressed position |
| Lab report claiming repetition cancels calibration uncertainty | 8.795 / 10.274 | Concern; distinguishes systematic calibration error from random variation and rejects zero uncertainty; no proposed partial-credit score |

These are observed outputs on five short synthetic PDFs, not a general accuracy rate or independent verification. Mathematical/uncertainty explanations are model reasoning, not execution-backed computation. The weak essay exposes a real classification error; null scores on observed concerns also show scoring conservatism despite performance descriptions. Teachers must verify and override. The pipeline's visual transcription may omit content; complete page transmission is not proof of complete semantic coverage. No benchmark establishes real handwriting performance.

Earlier evidence remains in [run-01](../artifacts/assessment-phase-4/run-01/report.json) and [run-02](../artifacts/assessment-phase-4/run-02/report.json). Run 01 rejected a strong-essay result with contradictory insufficient-evidence/score fields. A clarified prompt in run 02 produced a strength finding but joined a PDF line wrap in an evidence quote; exact-byte grounding rejected it. Run 03 validates whitespace-only equivalence and persists the exact source span. No scores, classifications or arbitrary model JSON were repaired to make a benchmark pass.

Synthetic future examples are defined for a misleading presentation chart, a research claim with incomplete reference evidence and a programming snippet with a supplied failed-test report. Their categories are tested as **unsupported**, not claimed as evaluated. The code snippet and supplied report are never executed or independently verified.

## Verification and limitations

The backend suite ran against a newly initialized disposable loopback PostgreSQL instance: **159 passed, 1 skipped**, with 21 dependency/lifecycle deprecation warnings. Only the opt-in paid Gemini live test was skipped. Coverage includes all three strategies through the same worker/contract, explicit approval, local provider selection even with an OpenRouter default, fabricated evidence/unknown pages/criteria, line-wrap grounding, score bounds/NaN, overrides/rejection history, confirmed-only insight counting, student/unrelated-teacher denials, partial coverage, failed-output preservation, local transport bounds/unloading, and additive migration replay. Existing budget races, billing ambiguity, permissions and student workflow tests pass. No production database was used.

Frontend: **12 tests passed**, including approval/decision cookie and same-origin protection. TypeScript checking and the Next production build passed. The synthetic teacher account was opened in a local Chrome window: login, private PDF rendering, assessment/evidence controls, manual scoring and collapsed diagnostics appeared in the accessibility tree; the narrow preview was visually inspected. The native browser surface became unavailable during wider-window checks, so a complete desktop interaction/visual regression pass is still outstanding. No UI publication was performed.

The full assessment service deliberately refuses non-PDF files, unsupported categories, over-budget contexts and partial sources. It provides no independently verified facts, citations, calculations, sandboxed tests or speaking-performance evaluation. Optional rubric drafting is covered by mocked transport; no separate real-model quality benchmark for drafted rubrics is claimed. Native slide/Word rendering, large/complex rubrics and long submissions require later work. Nothing was deployed and no paid API was invoked.

## Changed files for this milestone

- New `backend/services/assessment.py`: shared rubric/result contracts, strategy registry, versioned prompt, evidence/score checks and local reasoning orchestration.
- New `backend/assessment_models.py`, `backend/assessment_api.py`: immutable approvals/suggestions/teacher decisions, authorized local job requests, unpublished manual review reuse and confirmed-only historical insights.
- `backend/document_processing.py`, `analysis_api.py`: assessment tasks reuse durable quotas/leases/retries; extraction status remains separate from assessment status.
- `backend/services/ai_providers/engine.py`, `ollama.py`: explicit local configuration and reusable bounded structured completion using the shared model lock, preflight and unload policy. Gemini/OpenRouter implementations are preserved.
- `backend/main.py`, `permissions.py`, `persistence.py`, `migrations/__init__.py`: router/access integration and additive 009 registration.
- New `backend/tests/test_assessment.py`; `test_accounts_courses.py`, `test_academic_seed.py`: contract/workflow/security/migration regressions and migration count 9.
- New `backend/scripts/assessment_fixtures.py`, `benchmark_assessment.py`: known synthetic ground truth and isolated real-model workflow.
- New `frontend/src/components/assessment-panel.tsx`; teacher submission review page, `globals.css`, `frontend/tests/proxy.test.cjs`: rubric/feedback/confirmation/history UI, diagnostic disclosure, sticky original and proxy regression.
- `README.md`, this guide; synthetic `artifacts/assessment-phase-4/run-01`, `run-02`, `run-03`. All earlier Qwen/budget prototype work was retained.

## Phased rollout and future adapters

1. Review migration 009 and the UI/API diff; rehearse against a restored isolated staging database with cloud keys blank, `FORMA_AI_PAID_ENABLED=false`, `GEMINI_API_KEY=` and document workers initially disabled. Repeat migration application and run PostgreSQL regressions. Retain additive tables on rollback.
2. Pilot only on the developer Mac with the exact loopback Ollama model, one inference at a time and synthetic or institution-approved material. Enable the document worker locally. Teachers approve small explicit rubrics, verify original source quotations and score manually when the model abstains. Reproduce the five synthetic cases and finish desktop/mobile visual checks before wider use. The existing guarded launcher accepts the benchmark's ignored `runtime.env` using the same commands as the Qwen local guide.
3. Before production approval, decide where local inference will securely run. Render localhost cannot reach this Mac. This milestone does not supply a production inference network, tunnel or paid assessment transport. Do not expose Ollama publicly or copy its local settings to Render. Production enablement/deployment requires a separate reviewed architecture and explicit user authorization.
4. Add future `AssessmentStrategy` entries through the registry only after the evidence workflow is complete. Presentations need bounded safe slide rendering and chart/axis evidence, while speech/delivery stays unavailable without suitable media. Research assessment needs explicit retrieval/provenance adapters before any verified-reference status; otherwise citations remain unverified. Programming needs a separate authorized sandbox with resource/network/filesystem limits and tamper-resistant test receipts; never run submitted code in the FastAPI process. Each adapter should reuse the current rubric, evidence validation, immutable decisions and explicit publication flow.
5. Broaden to larger rubrics/documents only after context-coverage tests and human-reviewed evaluation. Any future cloud assessment transport must explicitly use the existing reservation/receipt ledger, key limits and privacy controls; it must not bypass the $4 application ceiling or introduce fallback.
