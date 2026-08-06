# Luna Safe Technical Repair V1

## Operating mode

The repair command is enabled automatically inside the consolidated episode
production worker. A local technical exception does not end the production
chain. Luna diagnoses the traceback, proposes the smallest exact-substring
change, SIRAJ validates it, applies it with a backup, runs verification, reloads
changed modules, and resumes the same production stage.

## Hard limits

- 3 Luna repair calls per consolidated production run.
- 0.05 USD per call, 0.15 USD total reserve.
- 2 proposals per unique failure.
- 5 files per repair.
- 200 changed lines per repair.
- Existing files only.
- One exact match per replacement.
- No Git commit or push during production.
- No dependency, architecture, public schema, budget, provider, model, policy,
  quality-threshold, religious-constraint, approved-content, lock, receipt,
  credential, or generated-media changes.

## Automatic continuation

A repair is accepted only after py_compile, compileall, focused pytest when
available, and git diff --check. Failed verification triggers an automatic
rollback. SIRAJ then asks Luna for one smaller proposal if budget remains.
After a passing repair, changed modules are reloaded and production continues.

## User-action stops

Production stops only for API keys, money/authorization, ambiguous provider
results, paid-task locks/retries, permissions, human review, protected files,
architectural changes, exhausted repair budget, dirty user-modified code, or
failure of both bounded repair proposals.
