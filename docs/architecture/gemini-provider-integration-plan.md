# Gemini provider integration plan

## Boundary

`GeminiSemanticProvider` implements `SemanticExtractionProvider` and is called
only by the cloud Critical-4 command. Historical ingestion, Gold annotations,
Shamela storage, graph construction, and documentary layers do not import the
adapter.

## Execution lifecycle

1. Load a credential-free Gemini configuration.
2. Resolve `GEMINI_API_KEY` from the process environment only.
3. Require explicit external-network and data-policy acknowledgements.
4. Prepare deterministic Critical-4 artifacts from existing Pilot-12 reports.
5. Invoke one route-specific structured generation request per case.
6. Validate literal evidence deterministically; allow one repair request only
   for schema or evidence failure.
7. Persist checkpoint, validation, usage, and comparison artifacts.
8. Mark the run pending human review; never accept a quality conclusion automatically.

## Provider choice

The adapter uses the official `google-genai` package. `generateContent` is used
within the adapter because it exposes JSON-schema structured output and usage
metadata required by Critical-4. The implementation does not use the legacy
`google-generativeai` package, Search grounding, web tools, NotebookLM, or any
fallback provider.

## Security and data-egress boundary

Only the official Gemini API host is accepted. External execution is denied
unless `external_network_allowed=true` and `data_policy_acknowledged=true`.
The key is never accepted from a CLI argument or JSON config and is redacted
before diagnostics or artifacts are produced. Free-tier traffic is explicitly
not assumed private.

## Test strategy

Focused tests use a fake transport and no environment key. They cover request
shape, Arabic UTF-8 preservation, structured parsing, error mapping, retry,
redaction, checkpoint/resume, and Critical-4 comparison preparation. Live
execution is manual only.
# Gemini schema integration diagnosis and closure

## Confirmed pre-fix fault

The Critical-4 adapter sent a raw `response_json_schema` dictionary to the
SDK. Its inherited local-provider schemas contained Gemini-incompatible
keywords and structures, including `additionalProperties`, numeric and string
constraints, bounded-array constraints, and a nullable `type` array. The
adapter then collapsed request-schema rejection, an empty response, malformed
JSON, response-model mismatch, and deterministic evidence rejection into the
single `GEMINI_SCHEMA_FAILURE` code.

## Closure

The adapter now sends only `types.GenerateContentConfig` with
`response_mime_type="application/json"` and exactly one `response_schema`.
Four route-specific Pydantic response models generate the schema. A local
sanitizer dereferences simple definitions, converts only a nullable scalar
union, and rejects any unsupported semantic keyword with its schema path.
The offline `schema-check` command verifies each final payload without an API
request. Real requests record a redacted local failure artifact with the exact
failure stage instead of relabeling it as a schema failure.
