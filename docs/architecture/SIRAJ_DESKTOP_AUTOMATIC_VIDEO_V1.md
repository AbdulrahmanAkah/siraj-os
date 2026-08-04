# SIRAJ Desktop Automatic Video V1

## Operator contract

The production operator performs only two actions:

1. Press **إنشاء الفيديو**.
2. After watching the downloaded result, enter one final integer score from
   `0` to `100`.

The generation button performs submission, async polling, download, hashing,
receipt creation, and crash recovery without further interaction.

After a successful download the interface exposes exactly the two requested
output actions:

- **عرض الفيديو**
- **عرض مكانه في الجهاز**

## Review contract

No category scoring, notes, or blocking-failure form is required.

- `80–100`: `PASS`
- `0–79`: `FAIL`

A failed score prepares the next deterministic attempt. Another paid request is
never launched in the background. Each paid attempt requires another explicit
press of **إنشاء الفيديو**.

## Attempt plans

1. Original approved shot package.
2. Continuity and material-physics repair prompt.
3. Simplified continuous documentary fallback.

Each attempt remains limited to one 8-second, 1280×720, no-audio result, with a
recorded cost ceiling of USD 0.40 per explicit click.

## Credentials

The Runware API key is configured once and stored in Windows Credential
Manager. It is not written to the repository, JSON receipts, logs, or Git.

If the program closes during an async task, pressing **إنشاء الفيديو** restores
the same task UUID instead of resubmitting it.

## Existing output migration

A successful V1 Beat 01 receipt is imported automatically as attempt 1. The
existing video immediately exposes the two output buttons and waits only for
the single final score.
