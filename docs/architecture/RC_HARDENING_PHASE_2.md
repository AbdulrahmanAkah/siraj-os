# RC Hardening Phase 2

SIRAJ remains `0.1.0-rc.1`. Phase 2 implements one real adapter only:
the OpenAI-compatible Responses HTTP API adapter in
`application.ai_provider_openai_compatible`. Its provider-specific transport,
response parsing, capabilities, error mapping, and request mapping do not
leak into domain layers.

## Credential and egress boundary

The adapter receives a `CredentialReference`, not a credential value. The
only environment-backed resolver lives in central configuration. The provider
never reads environment variables. External use requires explicit provider and
model allowlisting, `PUBLIC` or approved policy classification, explicit
network permission, and a credential reference. `RESTRICTED` data is denied.
Raw responses are hash-only by default and credentials are never logged,
persisted, serialized, or included in fixtures.

## Offline and live tests

The default suite uses a recorded in-memory transport and versioned fixtures;
it makes no network request. `external_ai` is an explicit opt-in marker and
currently skips without a separately supplied credential-enabled live setup.
The supported declared model is `gpt-4.1-mini`; capabilities are text,
structured output, citations, and multilingual text.

## Golden data and injection controls

Committed offline descriptors cover small historical, medium documentary, and
cross-era intelligence shapes. Gateway validation remains evidence-first:
unknown citations are rejected, unsupported claims are limited, contradicted
critical claims are rejected, and injection markers produce a validation
signal. Source text must be treated as untrusted data; this phase does not
claim complete prompt-injection prevention.

## Limits

No live provider is enabled by default, no automatic provider fallback or retry
exists, and no generated output becomes a source of historical truth. The
adapter validates only the documented response envelope; live provider fields
such as usage, timestamps, and request IDs are not deterministic replay keys.
