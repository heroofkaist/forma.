# Product audit fixes — 2026-10-15

This pass addresses B-01–B-05 from the supplied product audit. The existing visual identity, colours, typography and layouts are retained. The audit's longer product roadmap is not part of this change.

| Finding | Correction |
| --- | --- |
| B-01: inconsistent teacher review paths | Both course actions open the academic submission list. Old review/results URLs resolve through the authorized legacy-to-academic mapping and redirect to that same list. The legacy assignment index uses academic submission counts for mapped assignments. Independent scan assignments keep their existing workflow. Loading failures are shown as errors instead of an empty upload prompt. |
| B-02: AI state overrides a published human result | The student assignment page reads the published grade independently of analysis state. A published result takes precedence; its score, publication date and feedback remain visible after an AI failure. While awaiting publication, the page refreshes saved assignment/status data without triggering analysis. |
| B-03: technical criterion IDs | Published feedback uses descriptions and score bounds from the immutable review rubric snapshot. Historical records without a description receive a neutral numbered criterion label; current rubric edits never supply historical labels. |
| B-04: result is difficult to find | Assignment and grades views reuse one result component and the same backend serialization. The submission receipt and course list provide an explicit result link. Zero points remain a published grade, distinct from an ungraded submission. |
| B-05: raw analysis errors | The teacher submission list explains that analysis failed and manual review remains available. Operational details stay in existing teacher diagnostics. No retry or inference is triggered by viewing these pages. |

Authorization checks, private originals, drafts and deliberate publication are retained. Published criteria use only the linked published review, never a newer working draft. No migration, dependency, environment-variable or provider change is required. Rollout order remains backend first, then frontend; rollback uses the recorded prior application revisions and preserves the database and private storage.

Verification uses synthetic records and mocks only. Focused backend regressions cover route mapping/counts, authorization, published/unpublished visibility, zero scores, historical rubric changes and drafts. Frontend regressions cover readable criterion rendering, escaped feedback, publication precedence and review destinations. The existing draft/publication/provider suites are included. TypeScript and the OpenNext release build are checked.

Native Chrome inspection used an isolated local SQLite/storage copy, disabled workers and disabled paid inference. The student published result was inspected at 1440 and 390 CSS pixels, including the result link, wrapped feedback and criterion names. Both old teacher review/results routes redirected to the same saved submission. The teacher's failed-analysis message was inspected at desktop width. Captures are kept in the ignored `.local/audit-captures/` directory. The fixture's published result was seeded solely in this disposable synthetic database; no real grade was published. This is focused regression coverage, not a complete new product audit or cross-browser certification.

Final local checks: **82 backend tests**, **29 frontend tests**, TypeScript checking, OpenNext production build and `git diff --check`. Existing backend dependency/lifecycle warnings remain.
