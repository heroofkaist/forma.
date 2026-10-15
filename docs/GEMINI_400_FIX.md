# Gemini HTTP 400: isolated request incompatibilities

## Confirmed root cause

Controlled live requests against the locally configured `gemini-flash-lite-latest` alias, using installed **google-genai 1.75.0**, reproduced HTTP 400 with synthetic text alone. No student PDF, R2 access, job claim or database access was involved.

There are two independently demonstrated schema problems:

1. Pydantic `extra='forbid'` generates `additionalProperties: false` on Interpretation, Section and Association. The installed SDK's `response_schema` conversion accepts false locally (its unsupported-property guard tests truthiness) and serializes `additional_properties`. Gemini rejects that field with the allowlisted reason `Unknown name "additional_properties"` under `generation_config.response_schema`. Successful local SDK conversion was insufficient to establish server compatibility.
2. After removing that field, the document schema still returns 400/INVALID_ARGUMENT. Isolated reintroduction of either `sections.maxItems=1000` or `Association.section_ids.maxItems=1000` into an otherwise accepted schema independently restores the rejection. Removing the transmitted array upper bounds produces an accepted request. The server gives no more specific reason for this second rejection. This establishes which constraints trigger it on this schema/model; it does not establish that all uses of maxItems are unsupported, or prove the provider's internal decoder mechanism.

## Exact request inspected

The unchanged configuration is model `gemini-flash-lite-latest` (environment-configurable), `response_mime_type=application/json`, temperature 0.1 and max_output_tokens 12000. `contents` is one SDK-generated user content with source-page labels, optional inline image/png parts and the versioned text prompt. The application renders image-only PDF pages; it sends no raw PDF part, student identifier, R2 key or signed URL. Digital pages supply bounded extracted text. Source/question budgets, timeout and one SDK attempt are unchanged.

The live model metadata lookup succeeded, reported generateContent support, input limit 1,048,576 and output limit 65,536. Thus the tested 12,000-token output budget is within this alias's returned limit. The same model, temperature, MIME type and output budget work with a tiny schema. No model change or token-budget workaround is justified by this incident.

## Synthetic A/B evidence

Every request used synthetic instructions asking for a minimal empty interpretation, with no private documents. All other generation parameters were held constant.

| Schema variant | Result |
| --- | --- |
| Original Pydantic model via response_schema | 400; unknown additional_properties |
| Remove additionalProperties only | 400; INVALID_ARGUMENT |
| Tiny object/boolean schema, same other config | Accepted |
| Remove additionalProperties, default, minLength, maxLength, maxItems | Accepted; strict local validation passed |
| Restore default alone / minLength alone / maxLength alone | Each accepted |
| Restore maxItems constraints | 400 |
| Remove only additionalProperties and maxItems, retain all other constraints | Accepted; strict local validation passed |
| Restore sections.maxItems=1000 alone to that accepted schema | 400 |
| Restore Association.section_ids.maxItems=1000 alone | 400 |
| Remove only additionalProperties and the two 1000 bounds, retain smaller array bounds | 400 |
| Full original schema through response_json_schema instead | 400; switching the schema transport alone did not solve it |

After the patch, the real `gemini_interpret()` function also completed a live request with a generated two-page PDF containing digital text plus one image-only page. PNG rendering, SDK invocation, JSON decoding and strict evidence validation passed; teacher-review requirement remained true. The returned sections covered only the image page. That check establishes compatibility, not interpretation completeness or grading accuracy; teacher review and missing/ambiguous answer handling remain necessary.

Live probes used the existing locally configured Gemini credential solely for these bounded synthetic requests. Keys, full provider errors, prompts, model output and request bodies were not printed or saved. No private student documents or production application records were accessed.

## Implementation

`provider_response_schema()` builds a fresh schema from `Interpretation.model_json_schema()` and omits only `additionalProperties` and `maxItems` in the transmitted copy. Required fields, enums, nullable values, types, string lengths and numeric/page constraints remain. The Pydantic models themselves are unchanged: extras are still forbidden, array counts remain bounded and output still passes `validate_result()` before persistence. Known-question/page grounding, exact embedded-text evidence, visual-page authorization and teacher-only confirmation remain strict. No JSON-only fallback, schema-free retry, grade or correctness score was added.

The request/prompt compatibility version advances to `document-understanding-v2` for newly enqueued work/cache keys. Existing jobs and failed history are not rewritten. Future worker execution uses the compatibility adapter; failed jobs are not automatically requeued by this change.

Diagnostics add only canonical allowlisted provider statuses and fixed `UNKNOWN_SCHEMA_FIELD`/schema-field labels. No provider response or sanitized substring of arbitrary text is logged. Known rejected fields can be identified without exposing prompts, source content, identities or credentials. Generic INVALID_ARGUMENT remains generic when no allowlisted field is available; the logger does not invent a specific reason.

## Tests and rollout boundary

`PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q`: **94 passed, 7 skipped**, 21 dependency/lifecycle deprecation warnings. Six skips are PostgreSQL integration cases without a safe test URL; one is the new opt-in live synthetic compatibility test without `FORMA_TEST_GEMINI_API_KEY`. Separate explicitly requested live synthetic probes described above did run using the local configuration. `git diff --check` passed.

The new regression exercises the actual SDK HTTP serializer against a rejecting transport fixture, ensuring the request contains neither rejected wire field nor array upper bounds, and then verifies page/question associations. Additional tests prove local extra-field/array validation remains strict and provider diagnostics do not expose arbitrary response content. Existing processing, lease, authorization, PDF preview, retry and schema-migration tests pass.

After a separately approved backend deployment, the authorized teacher should use **Repeat analysis** on the existing submission. This sends `POST /api/document-analysis/{existing_submission_id}` with `{"reanalyze":true}`. Preserve the old failed job and original PDF; create a new bounded analysis version for the same submission through the existing permissions/quota checks. No new student upload is required. This action was not performed on production during implementation.

Deployed dependency versions/model alias resolution and real workload output quality still require production verification. The synthetic live request confirms the compatibility fix with the local SDK and current alias; it cannot prove every private PDF will produce semantically complete valid output. There was no deployment, production database update, infrastructure/configuration change or credential rotation.

## Changed files

- `backend/services/document_understanding.py`: separate compatible provider schema; request version v2; local validator unchanged.
- `backend/services/processing_diagnostics.py`: allowlisted provider reasons/known schema fields.
- `backend/tests/test_gemini_request_compatibility.py`: serializer, strict-validation/privacy regressions and opt-in synthetic live check.
- `docs/GEMINI_400_FIX.md`: evidence, limitations and authorized reanalysis procedure.

## Official references

Google documents a supported schema subset and cautions that complex schemas may be rejected; it also requires application validation of semantic values. These support retaining a separate strict local validator rather than assuming provider acceptance proves correctness. The exact rejected fields above were established by live A/B requests, not inferred from this general guidance. [Structured output support and limitations](https://ai.google.dev/gemini-api/docs/generate-content/structured-output).

Google recommends checking model token limits and feature/API-version compatibility for parameter failures. The local model metadata lookup and unchanged-parameter control request supplied that evidence here. [Gemini troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting).
