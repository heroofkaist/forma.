# Assignment-guided review and a shared course archive

Teacher requirements are captured with the reading/assessment job: assignment
description, questions, criterion identities and maxima, partial-credit rules,
evidence expectations and attached task sheets. Task-sheet proposals no longer
replace assignment question IDs or detach observations from the grading rubric.
The existing configured Qwen provider is reused unless assessment has an explicit
provider override. Uploading and viewing task files never starts inference.

The creation form supports a whole-work rubric (essay/report/project) and separate
problems with their own statements, maxima and subcriteria. Historical single-question
rubrics whose criteria explicitly identify numbered problems are grouped by those
problems, including labels such as «1 задача», regardless of a historic genre selection.
Ordinary essay criteria are different views of the same work. Reading instructions
avoid splitting every paragraph/equation into a separate answer. The interface
shows one task card and one row per source page; transcription correction and
fragment split/merge controls are inside the page's editing details.

Assessment uses existing teacher criteria without requiring them to be entered again.
The main grading tab has one explicit action, «Оценить по критериям». It shows a
proposed AI score beside each criterion and the AI total only when all criteria
have numeric scores. Missing scores stay empty, while a real zero remains zero.
Accepting/copying a proposal is an explicit teacher action; publishing remains a
separate confirmation. Polling new AI results preserves unsaved teacher values.

`POST /api/assessment/{id}` with `prepare: true` queues reading when needed, plus a
durable dependent assessment job in `awaiting_source`. The worker activates stage
two only after complete, hash-matching observations exist. It survives page closure,
serializes first-click races, reuses completed results on retries and exposes budget
pauses from either stage. The main action can resume within the existing allowance.
The daily limit remains 20 model stages per requester and three versions per task
kind/submission; reading and grading have distinct version counters. Local detector
jobs do not consume that model-job allowance. Every stage still uses the existing
hard dollar caps. Partial/failed reading never produces invented scores.

Strategies cover problem sets, essays, lab/research reports, slides, programming,
homework and general documents. Slide assessment cannot judge oral delivery and
code is never executed. Different question batches receive their own observed answers;
source quotes, IDs, point bounds and problem ownership are validated. Completed
batches are checkpointed before continuation, reusing the existing budget ledger.
The hard limits remain $4/month and $0.02/job. Large task contexts explicitly report
shortening; incomplete requirements cannot justify numeric model scores. Up to two
scanned task pages can be supplied as separate task images; these can never become
student evidence. OCR and grading quality remain model proposals for teacher review.

`015_shared_course_archive` adds only catalogue aliases and similarity corpus snapshots.
A course archive spans all cohorts and statuses of the same course. Verified courses
within the same institution and with the same normalized public catalogue code
share originals for comparison. A teacher may link their own course to another code
within that institution. Institution boundaries and access to private reviews/grades
are preserved. Shared archive endpoints expose originals/structure only, with other
teachers' student names and account IDs omitted from response metadata. A comparison independently authorizes every file.

Local text comparisons include the course archive by default, excluding the same
author. Previously completed/no-source runs refresh when the source corpus changes.
Failed/missing/in-flight states are preserved until an explicit refresh; they never
become successful zeros through a view. Every new corpus generation keeps the old
pair reports and teacher notes, while its snapshot identifies only current results.
The archive lists current and past files, filters by course, and opens a read-only
original or two files side by side. Historic work must already have been uploaded;
this change does not manufacture or import missing student records.

Single-work assignments need no manual page mapping. Multi-question assignments
can offer pages found by document reading, which the teacher can inspect and save.
Mappings remain a navigation aid and never alter grades.
