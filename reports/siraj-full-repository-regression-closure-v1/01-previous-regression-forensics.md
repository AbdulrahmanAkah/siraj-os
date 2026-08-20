# Previous regression forensics

- Command: `C:\SIRAJ\Repositories\historical-fixture-venv-20260716\Scripts\python.exe -m pytest -q`
- Collection: 1,157 nodeids.
- Prior interrupted evidence: 30 failure markers, 12 error markers, 1 skip, no final summary.
- Last completed node reconstructed from collection order: `tests/integration/test_shorts_desktop_ui_v1.py::test_shorts_dock_is_existing_window_surface_and_geometry_safe`.
- Exact hanging node established independently with faulthandler: `tests/integration/test_shorts_desktop_ux_screenshots_v1.py::test_short_ux_screenshots_are_captured_locally`.
- Minimal trigger: the hanging node alone while the Shorts dock is absent.
- Stack location: synchronous `QMessageBox.warning` in `src/presentation/desktop/main_window.py` after fail-soft Shorts initialization.
- Process state: one live Python process, no child process, no ffmpeg, and no useful forward progress until interruption.
- The original quiet interrupted run did not persist every marker's nodeid. This closure therefore reproduced the concrete failure families directly and then executed all 1,157 collected nodeids both by segment and in one completed full run.

Root-cause families reproduced:

1. Shorts profile authority drift: engine required `1.2.0`, while canonical profile and schema required `1.1.0`. This removed the dock and exposed an offscreen modal warning hang.
2. Canonical visual-context fixture drift: the fixture omitted required source `relevance_dimensions`.
3. OpenAI visual-context request test drift: the implementation intentionally bounded search and reasoning while the test asserted the older request shape.
4. Provenance error taxonomy regression: uncited HTTP sources were rejected by a generic reconciliation error before the specific citation verifier.
5. Release packaging environment defect: the session fixture reused repository `build/bdist.win-amd64`, causing `WinError 183` and nine dependent setup errors.

No failure was attributable to the canonical manual-visual pipeline.
