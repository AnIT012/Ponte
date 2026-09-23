"""整形のテスト。"""
import pytest

from ponte.fmt import FormatError, dwidth, format_source
from ponte.parser import parse


import glob

ALL = sorted(glob.glob("spec/*.ponte") + glob.glob("spec/*.ponte.ai/*.ponte") + glob.glob("ponte/std/**/*.ponte", recursive=True)
             + glob.glob("ponte/templates/*.ponte") + glob.glob("site/samples/*.ponte"))


@pytest.mark.parametrize("path", ALL)
def test_specs_are_formatted_and_idempotent(path):
    src = open(path, encoding="utf-8").read()
    assert format_source(src) == src               # もう整っている
    assert format_source(format_source(src)) == format_source(src)


def test_reindents_aligns_and_keeps_comments():
    src = """# 頭のコメント

thing A
    x   text   # 項目のコメント
    status[a | b]
## 承認待ち
list L
   of A
   where x is "1"
   sort x
match A.status to color
      a -> red
      b    -> blue
"""
    out = format_source(src)
    assert out.startswith("# 頭のコメント\n\nthing A\n  x  text  # 項目のコメント\n")
    assert "## 承認待ち" in out and "\n\n## 承認待ち\nlist L\n  of     A\n  where  x is \"1\"\n  sort   x\n" in out
    assert "\n  a -> red\n  b -> blue\n" in out
    assert parse(out).blocking == [(out.splitlines().index("## 承認待ち") + 1, "承認待ち")]


def test_display_width_counts_fullwidth_as_two():
    assert dwidth("ab") == 2 and dwidth("締切") == 4


def test_refuses_when_meaning_would_change(monkeypatch):
    import ponte.fmt as F
    monkeypatch.setattr(F, "_signature", lambda spec: [id(spec)])   # 前と後が必ず違う、とみなす
    with pytest.raises(FormatError):
        F.format_source("thing A\n  x text\n")
