# ElevenLabs Key Validation and Recovery V1

This release prevents SIRAJ from submitting an ElevenLabs request when the supplied credential does not use the currently required `sk_` prefix.

## Runtime behavior

1. Validate a newly entered ElevenLabs key before saving it.
2. Validate environment and Windows Credential Manager values before use.
3. Validate again immediately before creating a paid-attempt lock.
4. Classify HTTP 400 `invalid_api_key_prefix` responses as terminal, non-billable authentication rejections.
5. Archive the rejected lock and require a new valid key plus a new explicit authorization.
6. Preserve every completed Runware, ElevenLabs and local-graphics output and receipt.

No key value is written to project files or reports.
