# Adam Partial Source Resolution and Human Review Docket v1

This stage performs deterministic refinement of the five source candidates that
remained partial after remote materialization and bounded text comparison.

The refinement uses Arabic normalization, light clitic and suffix handling,
fuzzy token alignment, token-order preservation, sequence similarity, and
character trigram similarity. A source may be rerouted from targeted resolution
to refined human confirmation, but no machine result becomes verified evidence.

The stage also creates the final blank human review docket for all twenty-two
sources. Each decision must use one of four explicit outcomes:

- `confirm_exact_source_text`
- `confirm_with_correction`
- `reject_locator`
- `defer_authentication`

The decision layers remain separate: exact text and locator, hadith
authentication, source-origin classification, event narration disposition, and
episode evidence approval.

For sources still unresolved, a bounded NotebookLM prompt pack is generated.
NotebookLM may assist source comparison but cannot replace human verification.

The evidence gate and live providers remain blocked.
