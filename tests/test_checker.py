"""仕様 v0.2 のエラーごとに「わざと壊した仕様」と「直した仕様」のペア。

tests/cases/<コード>_<名前>/broken.ponte  … 必ずそのコードで止まる（W は警告として出る）
tests/cases/<コード>_<名前>/fixed.ponte   … エラー0件、そのコードも出ない
  publish          があれば公開する時の検査（E26）
  prev.shape.json  があれば前回のビルドの thing の形（E21）
"""
import json
from pathlib import Path

import pytest

from ponte.checker import ALL_CHECKS, Options, check
from ponte.parser import parse_file

CASES = sorted(p for p in (Path(__file__).parent / "cases").iterdir() if p.is_dir())


def run(case: Path, which: str) -> list[str]:
    prev = case / "prev.shape.json"
    opt = Options(publish=(case / "publish").exists(),
                  prev_shape=json.loads(prev.read_text(encoding="utf-8")) if prev.exists() else None)
    return [f.code for f in check(parse_file(str(case / which)), opt)]


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_broken_stops(case):
    code = case.name.split("_", 1)[0]
    found = run(case, "broken.ponte")
    assert code in found, f"{code} で止まるはずが {found}"


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_fixed_passes(case):
    code = case.name.split("_", 1)[0]
    found = run(case, "fixed.ponte")
    assert not [c for c in found if c.startswith("E")], found
    assert code not in found, found


def test_every_error_code_has_a_case():
    codes = {c.name.split("_", 1)[0] for c in CASES}
    expected = {f"E{i:02d}" for i in range(1, 33) if i != 9} | {"W09", "W26"}
    assert expected <= codes, sorted(expected - codes)
    assert len(ALL_CHECKS) == 36


def test_spec_appendix():
    """仕様書 v0.2 の付録そのままは tbd だけで止まる。外した版は公開の検査まで通る。"""
    found = [f.code for f in check(parse_file("spec/hub.ponte"))]
    assert found == ["E05"], found
    found = [f.code for f in check(parse_file("spec/hub_ready.ponte"), Options(publish=True))]
    assert found == [], found
