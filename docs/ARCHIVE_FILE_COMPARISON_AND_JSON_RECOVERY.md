# Archive file evidence and structured-output recovery

## Failure addressed

The supplied production trace for job `77b496de-d3cb-4329-9812-84ee600b86cd`
failed at `openrouter_decode` inside `json.loads` during document reading. The
successful HTTP GETs were progress polling, not successful grading. The trace
does not reveal the malformed response, so its exact syntax cannot be diagnosed
from that log alone.

OpenRouter's free response-healing plugin is now requested alongside strict JSON
Schema. A shared local decoder accepts a single complete object with a BOM, a
completed reasoning wrapper, a complete Markdown JSON fence or short prose
prefix. It preserves strings exactly. Duplicate keys, multiple objects,
incomplete data, nonfinite constants and incomplete fences are rejected. The
existing schema, question/page ownership and evidence-grounding checks still run.
Non-stop cloud completions cannot pass as completed document readings. No paid
resend or fallback is added. Billing remains reserved and reconciled as before.

JSON failures receive a fixed Russian hint, which is also propagated from a
failed reading job to the dependent grading job. Originals and previous results
are retained. A previously failed production job needs an explicit retry after
deployment; the missing model response cannot be reconstructed from its log.

Reference: [OpenRouter response healing](https://openrouter.ai/docs/guides/features/plugins/response-healing),
[pricing and scope announcement](https://openrouter.ai/blog/announcements/response-healing-reduce-json-defects-by-80percent/).
The plugin addresses formatting, while application validation determines whether
the result is usable. It does not make model observations independently verified.

## Comparison methods

The earlier archive report compared extracted text. The separate selected-file
comparison used lexical TF-IDF and coarse page thumbnails. The course archive
now has a resumable whole-file comparison that uses:

* Exact file hashes for byte identity, with blank/common-only content guards.
* Word winnowing (7-word shingles, 5-shingle windows) for long copied passages,
  with a minimum 11-word match and exact original excerpts, offsets and pages.
  Paragraph rearrangement and case/whitespace changes do not hide a retained
  passage. Matching teacher task material is excluded. Work/output caps mean
  this bounded implementation does not promise an unrestricted recall guarantee.
* ORB local image features with bidirectional descriptor matching, a ratio test,
  RANSAC homography, inlier/spread checks and bounded original-page regions.
  This can identify copied scans after crop, rotation or moderate changes in
  perspective. Equal raster pages are also recognized. A single matching page
  is aggregated across both documents, rather than becoming a whole-file 100%.
* Existing normalized code/AST features and formula-string comparison. Formula
  overlap remains supplemental: it does not prove algebraic equivalence or
  copying. Code is never executed. Lexical TF-IDF is also supplemental and no
  longer determines the combined file index.

References: [Schleimer, Wilkerson and Aiken, SIGMOD 2003](https://theory.stanford.edu/~aiken/publications/papers/sigmod03.pdf)
and [OpenCV feature matching and homography](https://docs.opencv.org/4.x/d1/de0/tutorial_py_feature_homography.html).
Winnowing motivates localized, position-independent text evidence; OpenCV
documents geometric verification of local image correspondences. The thresholds
here are engineering choices covered by synthetic regressions, not a validated
plagiarism classifier or measured accuracy on student handwriting.

Known assignment sheets and linked required/optional templates supply text and
visual exclusions. Exact task lines can be masked in the comparison raster;
geometrically matching baseline features are removed. Original files are never
edited. Limits on teacher context or baseline count are disclosed in the report.

## Archive coverage and instructor controls

`GET /api/assignment-comparison/archive/{submission_id}` reads saved receipts.
`POST` checks the next missing candidate. A scan covers other authors across all
cohorts and verified linked courses in the same institution's archive; all of the
current student's previous attempts are excluded. File scans are independent of
the old text-only report, so raster PDFs with no extracted text can participate.

Each completed pair is stored in `AssignmentComparison`. Reloading resumes the
coverage; the reversed pair can reuse the same unchanged result. No migration or
model call is required. A changed corpus, original hash/structure, assignment
requirements or task/template snapshot makes the archive receipt stale. Concrete
source authorization is checked before and after computation, including reuse.
Cross-course source identities retain the existing archive anonymization policy.

The student roster and archive show saved file-match flags. Instructors can start
one scan or check all current works with one button, stop after the current file,
and resume later. Failed inputs remain unavailable and explicitly incomplete;
they are never silently counted as 0%. Unavailable candidates can be retried.
Only positive matches appear as source cards; the report separately counts
processed, comparable, pending and unavailable files.

Red means a match requiring review. It does not determine which author borrowed
from whom or whether the match is permitted. This follows the distinction in
[Turnitin's instructor guidance](https://guides.turnitin.com/hc/en-us/articles/23435833938701-Understanding-the-similarity-score).
The report links exact passages and matching image regions to the two originals.
Small positive indices display as `<1%`, and stale or unavailable data do not
appear as current zeroes or red findings.

## Resource and interpretation limits

The local subprocess retains 30-second wall/25-second CPU bounds, a Linux memory
ceiling, a single concurrent comparison slot per server process, 60 MB of input,
200 pages/images, and 50 pages per PDF. BLAS/OpenCV run with bounded threads.
There are up to six baseline files/15 MB and 20,000 teacher-context characters.
Archive scans continue one candidate at a time, with an explicit progress count;
the endpoint permits 120 steps per identity per 15 minutes. Saved progress
survives a pause or page close. The monthly $4 language-model budget is unchanged.

PDF pages and DOCX/PPTX embedded PNG/JPEG images are supported. Complete DOCX/PPTX
page layout is not rendered. Rewritten handwriting, substantial visual changes,
semantic paraphrase and translation may evade these methods. Common formulas,
legitimate quotations and authorized collaboration still need instructor context.
These are file-comparison tools for academic review, not an automatic misconduct
decision or a forensic handwriting-authorship system.

Regression coverage includes wrapped/invalid JSON, no additional paid dispatch,
error propagation to grading, rotated/cropped raster copies, unrelated drawings,
shared template removal, reordered passages, exact offsets, archive continuation,
cache reuse, inaccessible inputs, privacy and stale receipts. All provider calls
in tests are synthetic; no live AI tokens are spent.
