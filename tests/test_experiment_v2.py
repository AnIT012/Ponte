"""比較実験 v2 の採点が正しいことの確かめ。両方の条件の参照実装（人が書いたもの）が14個全部通る。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path("experiment/v2")))
import harness  # noqa: E402


def test_reference_a_passes_all():
    res = harness.run(harness.load_a(Path("experiment/v2/reference/system_a.py")))
    assert all(ok for _, ok, _, _ in res), [r for r in res if not r[1]]


def test_reference_b_passes_all():
    code = open("spec/hub_app.lang.ai/ExtractDeadline.lang", encoding="utf-8").read()
    res = harness.run(harness.load_b(code))
    assert all(ok for _, ok, _, _ in res), [r for r in res if not r[1]]


def test_a_broken_color_is_one_bug(tmp_path):
    src = Path("experiment/v2/reference/system_a.py").read_text(encoding="utf-8").replace('"passed": "green"', '"passed": "blue"')
    p = tmp_path / "s.py"
    p.write_text(src, encoding="utf-8")
    fails = [n for n, ok, _, _ in harness.run(harness.load_a(p)) if not ok]
    assert fails == ["色の表（それ以外は gray）"]
