# Forma: reading room redesign

The homepage and login now follow the [MotionSites public reference direction](MOTION_PUBLIC_REDESIGN.md). This document continues to describe the teacher/student workspace system and established account pages.

The primary task is to find a student's work, assess it against the assignment criteria, and publish an understandable result. The redesign uses a paper background, dark readable text, a restrained forest accent, and a shared component vocabulary across teacher, student, account, archive, and public pages.

## Evidence and scope

The evidence is the existing application and the user's repeated reports: overloaded teacher pages, unclear controls, unwanted disclosure triangles, repeated routes to the same destination, difficulty finding AI criterion scores, and uncertainty about repeated AI charges. This is a heuristic review and a task walkthrough, not a study with recruited teachers. No measured improvement in completion time or teacher satisfaction is claimed.

The product outcome is easier completion of the review workflow. A useful later validation is to observe teachers finding a student, explaining an AI proposal, changing a criterion score, and publishing a result without assistance. Record completion, wrong turns, accidental reanalysis attempts, and whether they understand when students see grades. Use synthetic work and obtain consent before recording a session.

## All nine requested skills

Source: `~/Downloads/frontend-agent-skills-main/`. Each skill's `SKILL.md` was opened and used; the folder's checklists informed the implementation and review.

| Skill | Applied decision | Verification |
| --- | --- | --- |
| ux-usability-foundations | One visible next task on the teacher dashboard; empty, loading, error, and retry states; duplicate submission guard | Course creation, queue recovery, and empty-search checks |
| information-architecture-navigation | Courses → assignments → student work → review; task-based primary navigation; contextual return links; fewer duplicate assignment links | Known-item lookup, exploratory course browsing, and recovery walkthroughs |
| ui-visual-composition | Shared paper, ink, forest, and status colors; quiet panels; readable UI typography; distinct title and action hierarchy | Desktop and phone screenshot inspection |
| interaction-patterns-components | Tables for comparative records, labelled disclosures for secondary operations, separate original and grading panels | Review tab keyboard checks; open and close assignment form |
| forms-inputs-checkout | Persistent labels, grouped assignment fields, optional files, show-password control, submit validation that explains the problem | Duplicate create guard, preserved input after error, labelled native controls |
| accessibility-inclusive-design | Skip links, landmarks, active navigation state, visible focus, native inputs, reduced motion, text labels for status | Keyboard walkthrough; viewport overflow, accessible-name, and token contrast checks |
| ux-writing-content-design | Plain Russian, named outcomes, actionable errors, explicit stored AI result and publication visibility | In-context reading of teacher, student, login, and review pages |
| design-systems-frontend-architecture | Semantic tokens and shared component styling; one product example reused on landing and account entry; local fonts and existing icon library | Type checking and Cloudflare production build |
| ux-research-discovery-testing | Evidence separated from assumptions; realistic task walkthroughs using synthetic data; limitations and follow-up study defined | Documented tasks below; no fabricated participant results |

## System contract

`frontend/src/app/product-design.css` is the migration boundary for the refreshed system. `identity.css` retains established component and responsive rules with a migrated palette; `globals.css` retains legacy layout primitives. New public components use `public-*` and `tour-*` names. New product styles should use purpose-based selectors and semantic tokens rather than new raw palette values or deeper location selectors. Consolidate a legacy rule when its component is next changed.

- Primary action: forest fill, visible outcome, at least 44 px high. Secondary action: neutral border. Navigation uses links; mutations use buttons.
- Panels: shared border, radius, and restrained elevation. Comparisons keep status text alongside color. Red means a found match or an error; it does not establish misconduct.
- Typography: locally hosted IBM Plex Sans for the interface; Cormorant Garamond only for short editorial accents. Numbers use normal or tabular figures. Student originals and quotes are unchanged.
- Forms: labels stay visible; field groups follow task order. Optional assignment sheets and templates remain optional. Template requirement is selected only after a file is chosen. Failed requests preserve entered values.
- Disclosures: native `details/summary` with visible “Показать / Скрыть”; no tiny triangle or plus/minus expansion controls. Plus icons only identify additive actions such as creating a new stream.
- Review: AI scores remain beside criteria. Saved scores are identified as saved; reanalysis is explicit and visually secondary. Manual grading, evidence, drafts, unsaved-change protection, and publication confirmation remain available.
- Responsive navigation: the teacher rail becomes a horizontally scrollable labelled navigation row. The mobile focus view keeps the review's contextual return link and original/grading tabs. Data rows become labelled records where simultaneous columns no longer fit.
- Accessibility: semantic controls, active navigation text/state, focus rings, native keyboard behavior, polite status updates, reduced motion, and forced-colors selected indicators. Avoid adding custom controls without a complete keyboard and focus contract.

## Walkthrough and verification

Use synthetic students, scores, course names, and files. Intercept API requests during browser design QA; reject non-GET requests so previews cannot grade, publish, or spend tokens.

1. **Known item:** open My courses, search by course name/code, open assignments, open student work, locate the original and the proposed criterion score.
2. **Explore:** browse multiple courses, check deadlines and submission counts, inspect optional assignment instructions, compare archive evidence and open source files.
3. **Recover:** search for an absent course/student, reset the query, retry a failed queue load, and retain the entered stream after a create error.
4. **Review:** use keyboard arrows to switch grading/conditions/tools, verify focus and visible content, inspect saved AI results, and keep publication separate from drafting.
5. **Responsive:** inspect 1440 px, 768 px, and 390 px; test long course names and file names; check that document-level width does not overflow.
6. **Account:** use visible email/password labels and the password visibility control. Retain credentials on a recoverable sign-in error. Never store preview credentials or tokens in artifacts.

Automated checks: frontend suite, TypeScript, Cloudflare production build, diff whitespace check. Browser checks cover the landing page, login, teacher courses, course assignments, assignment form, student list, review, student dashboard, and saved archive comparison. Browser previews use synthetic API responses and make no paid AI requests.

Contrast spot checks for the main tokens: ink/page 13.45:1, secondary/page 5.47:1, white/primary 7.01:1, primary/selected 6.18:1, error/error-surface 6.47:1. Muted and placeholder text were darkened after checking. These checks and keyboard walkthroughs are not a full WCAG conformance audit or a screen-reader study.

## Visual references

Synthetic data only. The screenshots show representative templates, not proof of production deployment.

- [Homepage](design/reading-room/home-desktop.png)
- [Teacher courses](design/reading-room/teacher-desktop.png)
- [Review workspace](design/reading-room/review-desktop.png)
- [Phone layout](design/reading-room/teacher-mobile.png)

## Release boundary

This is a frontend redesign. It does not change AI models, budgets, inference triggers, cached assessment storage, archive algorithms, access policy, or grading authority. Commit and push through the established main-branch autodeploy workflow. No manual deployment is required.
