
from pathlib import Path


def test_v13_title_contract_retained_only_as_compatibility_marker():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo / "src/presentation/desktop/main_window.py"
    ).read_text(encoding="utf-8-sig")

    legacy = 'setWindowTitle("سراج — إدارة إنتاج الحلقات — v1.3")'
    current = 'self.setWindowTitle("سراج — Production Studio — V6.5")'

    assert legacy in source
    assert current in source

    # The old source-contract string must be retained as a comment only,
    # not restored as the actual runtime window title.
    assert (
        '# Legacy v1.3 source-contract marker: '
        + legacy
    ) in source
    assert (
        '        setWindowTitle("سراج — إدارة إنتاج الحلقات — v1.3")'
        not in source
    )
