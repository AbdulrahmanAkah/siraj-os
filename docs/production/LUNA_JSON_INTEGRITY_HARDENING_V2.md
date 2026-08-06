# Luna JSON Integrity Hardening Before Retry

The first Luna provider request returned text, but the old executor attempted
JSON parsing before persisting the raw provider response. That first response
cannot be recovered from local artifacts.

This repair makes no provider request. It:

- reads only `message/output_text` parts;
- ignores reasoning text and other response items;
- accepts one accidental JSON code fence;
- checks response status and incomplete details;
- persists the full raw response before extraction or parsing;
- writes a diagnostic record on every parse failure;
- reduces reasoning effort from high to medium;
- reduces output verbosity from high to low;
- preserves the strict JSON schema and the 95/100 quality gate;
- leaves the failed lock untouched;
- requires separate explicit authorization before one replacement request.
