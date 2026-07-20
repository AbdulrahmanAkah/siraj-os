# Gemini semantic provider — Critical-4 only

This adapter is restricted to the four audited Critical-4 cases. It uses the
official `google-genai` SDK and the `generateContent` API inside the adapter.
`generateContent` is selected because its JSON-schema response configuration
and usage metadata are directly supported by the current bounded extraction
contract. No legacy `google-generativeai` package is used.

## Install

```powershell
python -m pip install -e ".[gemini]"
```

## Configure credentials

Set the key only in the process environment. Do not put it in configuration,
arguments, test fixtures, logs, or artifacts.

```powershell
$env:GEMINI_API_KEY = "your-key"
```

Copy `gemini-provider-config.example.json` to a local ignored location and
review its external-network and data-policy acknowledgements. Free-tier data
must not be assumed private; use only content allowed by the applicable data
policy.

## Status without an API call

```powershell
siraj semantic cloud gemini status --config C:\safe\gemini-provider-config.json
```

This checks configuration and the presence of `GEMINI_API_KEY`; it does not
send a request.

## Offline schema check

```powershell
siraj semantic cloud gemini schema-check --config C:\safe\gemini-provider-config.json --sample critical-4
```

This command sends no request. It writes `gemini-schema-check-report.json`
next to the local configuration file and verifies all four minimal Pydantic
response models after Gemini-subset schema sanitization.

## One-request schema probe

Run this only after the offline check passes. It sends one fixed, safe Arabic
sentence through the `PERSON_AND_STATUS` schema and reports the finish reason
and parse result. Do not pass Arabic text through a PowerShell pipe.

```powershell
siraj semantic cloud gemini probe --config C:\safe\gemini-provider-config.json --route PERSON_AND_STATUS
```

## Manual Critical-4 run

```powershell
siraj semantic cloud critical-regression run --semantic-root C:\SIRAJ\Workspace\first-project\working\local-semantic-intelligence --sample critical-4 --provider gemini --config C:\safe\gemini-provider-config.json
```

The run is serial, uses one request per case in normal operation, and permits
one repair request only after a structured-output or literal-evidence failure.
It writes provider-specific manifests below `pilot-12/critical-4/`. A completed
run remains pending human review and makes no automatic provider-quality claim.

## Error codes

- `GEMINI_API_KEY_MISSING`: set the environment variable for the current process.
- `GEMINI_AUTH_FAILED`: verify the key outside Siraj; never paste it into logs.
- `GEMINI_MODEL_NOT_AVAILABLE`: choose a model returned by the provider account.
- `GEMINI_QUOTA_EXCEEDED` or `GEMINI_RATE_LIMITED`: wait or adjust the account quota.
- `GEMINI_REQUEST_SCHEMA_REJECTED`: Gemini rejected the request schema before generation; inspect `gemini-critical-4-last-failure.json` and do not retry the same schema.
- `GEMINI_EMPTY_RESPONSE`: the response had no text despite a request completing.
- `GEMINI_FINISH_REASON_FAILURE`: the finish reason was not `STOP`.
- `GEMINI_JSON_PARSE_FAILED`: the provider text was not a JSON object.
- `GEMINI_RESPONSE_SCHEMA_MISMATCH`: JSON parsed but did not match the route response model.
- `GEMINI_EVIDENCE_VALIDATION_FAILED`: JSON matched the model but literal evidence validation failed.
- `GEMINI_SAFETY_BLOCK`: do not retry automatically.

Remove the variable when finished:

```powershell
Remove-Item Env:GEMINI_API_KEY
```
