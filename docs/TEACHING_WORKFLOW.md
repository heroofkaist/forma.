# Teacher workflow and readable AI feedback

The assignment workspace has three views: student work, teacher rules for AI,
and the cohort summary. Existing grades are never overwritten by these views.

## Teacher standards before inference

The rubric editor explains evidence requirements and partial credit, warns about
vague task labels and excessive criterion totals, and supports up to 12 criteria
for AI assessment. More complex existing assignments remain manually reviewable.

Teachers can save criterion-specific rules, a feedback focus and up to five
confirmed reference reviews from this assignment. This is prompt calibration,
not model training. Each change creates an immutable `TeachingGuide` version.
Concurrent saves require the previous version ID. Changing the assignment or
effective approved rubric makes the old guide inactive until reviewed and saved.

The model receives only matching rules and bounded reference excerpts/scores.
Reference submission names and IDs are omitted; known student names and IDs are
redacted from excerpts and comments. Teachers should still review excerpts for
other personal information. The target submission is excluded from its own
examples. Incompatible reviews and stale/incomplete document readings cannot
supply answer excerpts. Optional examples are dropped if necessary to preserve
the current answer and mandatory rules within the existing request budget.

## Assessment and evidence

Numbered problem groups are evaluated independently. Evidence must still match
an exact observed source span, page and question; a reference example can never
serve as evidence for the current student. The prompt asks for a reason tied to
the awarded points and one actionable improvement, in Russian.

Generated placeholders, control characters and raw JSON in explanation fields
are removed. An unusable rationale or nonfinite model score causes that score
to be withheld. Original student text, evidence quotes and teacher comments are
not rewritten. Existing strict evidence and range validation remains in place.
UI score formatting preserves zero, rounds display precision to two decimals
and displays unavailable/out-of-range values as a dash.

An individual criterion can be rechecked using a saved suggestion. Other scores
are reused only when the approved rubric, assignment/task files, source reading,
correction and teaching guide snapshot are unchanged. The new full suggestion is
strictly revalidated and stored as a separate version. A changed snapshot requires
a full recheck. Daily and monthly cost limits still apply. Viewing saved results,
guides, summaries, citations and revision differences makes no model call.

Clicking an evidence citation shows its page and quote. The authorized backend
locates a unique embedded-text match in the immutable original PDF and returns
normalized rectangles, including rotated-page coordinates. Scans or ambiguous
matches show the page/quote without invented highlighting. Non-PDF originals
retain the download workflow.

## Teacher review and group feedback

The roster filters work requiring attention, including failed/paused processing,
criteria without model scores, incomplete teacher drafts and stale AI results.
Confirmed teacher reviews resolve AI attention warnings. The question workflow
supports previous/next student links, an individual criterion filter and Alt +
arrow keys. Existing unsaved-change protection applies to those links. Manual
page mappings take priority; fresh OCR page associations are labeled as inferred
and serve only for navigation. A single whole-work question needs no page mapping.

The criterion editor can load saved comments from compatible confirmed review
cards. Inserting text never copies the card's historical score or claims new
source evidence. The existing provenance-based card workflow remains available.

The cohort summary uses only the latest attempt per student whose latest review
is fully confirmed against the current effective rubric. Drafts and AI-only scores
are excluded. It shows each criterion's denominator, average, count below full
credit, exact normalized teacher comments repeated across at least two works,
and authorized links to examples. A lower score does not infer a misconception.

## Resubmission

Published feedback exposes its immutable review ID consistently in all student
grade views. A student may attach a response identifying published criteria and
explaining changes to a permitted resubmission. The response and upload receipt
are stored atomically; retrying the same receipt cannot duplicate the attempt or
silently change the explanation. Existing availability, deadline, enrollment and
resubmission checks still apply. Teachers can view the frozen earlier comments,
student response and bounded extracted-text diff (20,000 characters per original,
250 diff lines). This does not claim to compare all formulas or scan images.

Students also see a published teacher comment from the first below-full-credit
criterion as a focus for further work. It is not newly generated or published AI
feedback.

## Deployment and checks

Migration `016_teaching_workflow` adds two tables without rewriting grades,
originals or prior interpretations. Deployment uses the existing push-to-main
automation. No new provider, secret or paid detector is required; the configured
$4 monthly AI budget and per-job reservation limits remain unchanged.

Regression tests cover version conflicts, reference eligibility, self-exclusion,
snapshot-safe criterion rechecks, exact citation locations, unreadable model
explanations, cohort denominators, private access and atomic resubmission retries.
These verify application behavior with synthetic provider responses; they do not
measure the live model's pedagogical accuracy. Frontend tests and the Cloudflare
build verify the browser contracts; synthetic desktop/mobile previews verify layout.
