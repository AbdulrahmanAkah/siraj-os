# Explicit Luna Invalid-Output Retry V2

The first Luna batch is locked with:

`INVALID_LUNA_OUTPUT_NO_AUTOMATIC_RETRY`

That lock is intentional. It proves that no hidden paid retry occurred.

This recovery layer adds one state-aware desktop authorization:

- the existing consolidated button changes to an explicit Luna retry action;
- the protective maximum increases from 34.864375 USD to 34.914375 USD;
- the extra authorization is exactly 0.05 USD;
- the original failed lock is archived before the replacement request;
- the supplemental authorization is consumed before network activity;
- only one replacement request can be made;
- a second failure remains locked and requires manual review;
- automatic and hidden retries remain forbidden;
- the total remains below the 40 USD episode hard cap.

Installing this layer performs zero provider requests.
