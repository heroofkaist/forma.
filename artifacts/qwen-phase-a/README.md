# Synthetic Qwen Phase A benchmark

These artifacts contain generated coursework only. No private student PDFs, credentials, prompts from real coursework or production data are included.

- `run-01`: initial direct shared-schema attempt; failed strict duplicate-section-ID validation. Raw response and failure report are retained.
- `run-02`: final provider-specific observation adapter; all three PDF pages rendered, observed and strictly validated. `report.json` includes actual job/review results and timings; `raw-responses.json` contains real local model responses; `memory-samples.json` contains sampled RSS and API allocation; `environment.json` records non-sensitive hardware/model metadata; `http-review-check.json` records the real local proxy/private-PDF check.
- Each PDF is the original generated input for its run. Generated SQLite databases, private storage copies and local runtime environment files are gitignored and remain available locally for review; they are not portable release artifacts.

See [setup and limitations](../../docs/QWEN_LOCAL_ENGINE.md). No accuracy score is claimed. Generated handwriting is a font-based approximation, and the final model output omitted the intentionally blurred patch. Page-level schema validity is not proof of complete or correct mathematical interpretation.
