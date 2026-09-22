"""エラーごとに「わざと壊した仕様」と「直した仕様」のペア。

tests/cases/<コード>_<名前>/broken.spec  … 必ずそのコードで止まる
tests/cases/<コード>_<名前>/fixed.spec   … エラー0件で通る
"""
from pathlib import Path

import pytest

from lang.checker import check
from lang.parser import parse_file

CASES = sorted(p for p in (Path(__file__).parent / "cases").iterdir() if p.is_dir())


def codes(path: Path) -> list[str]:
    return [f.code for f in check(parse_file(str(path)))]


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_broken_stops_with_expected_code(case: Path):
    expected = case.name.split("_", 1)[0]  # 例 E01 / W09
    found = codes(case / "broken.spec")
    assert expected in found, f"{case.name}: {expected} で止まるはずが {found}"


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_fixed_passes(case: Path):
    found = codes(case / "fixed.spec")
    errors = [c for c in found if c.startswith("E")]
    expected = case.name.split("_", 1)[0]
    assert not errors, f"{case.name}: 直した仕様にエラーが残っている {found}"
    assert expected not in found


def test_hub_ready_passes():
    found = codes(Path("spec/hub_ready.spec"))
    assert not [c for c in found if c.startswith("E")], found


def test_hub_verbatim_stops_as_designed():
    """仕様書の例そのままは unknown / proposed / use(△) で止まる。これは狙いどおり。"""
    found = codes(Path("spec/hub.spec"))
    assert "E05" in found and "E06" in found and "E03" in found and "E04" in found
