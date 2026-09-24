"""ドキュメントの日本語が docs/文章の書き方.md に沿っているか（表記と記号だけ。文体の細かい所は人と textlint で見る）。"""
import html
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ["README.md", "docs/入門.md", "docs/言語仕様_v0.3.md", "docs/仕組み.md", "docs/文章の書き方.md", "docs/IR.md"]
PAGES = ["site/landing.html"]

# (見つけたらだめな形, 直し方)
BAD = [
    (r"—", "ダッシュは使わない"),
    (r"★", "記号で飾らない"),
    (r"無[いくかけし]", "「ない」とひらがなで"),
    (r"出来[るたなま]", "「できる」とひらがなで"),
    (r"下さい", "「ください」"),
    (r"[るたいな]時[、。はにもでの]", "「とき」とひらがなで"),
    (r"[るたいなの]事[、。はがをにもで]", "「こと」とひらがなで"),
    (r"全部", "「すべて」"),
    (r"要る", "「必要です」"),
    (r"決めごと", "「仕様」"),
    (r"箱", "「レコード」"),
    (r"なので", "「そのため」"),
]


def prose(text: str) -> str:
    """コード（``` と `…`）と、表記の例を並べた表の行を除いた本文"""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"<!-- 自動.*?自動（ここまで） -->|<!-- 自動: エラー（ここから）.*?（ここまで） -->", "", text, flags=re.S)
    return "\n".join(re.sub(r"`[^`]*`", "", l) for l in text.split("\n"))


def page_text(path: Path) -> str:
    t = path.read_text(encoding="utf-8")
    t = re.sub(r"<(script|style|pre)[^>]*>.*?</\1>", "", t, flags=re.S)
    return html.unescape(re.sub(r"<code>.*?</code>|<[^>]+>", "", t))


@pytest.mark.parametrize("path", DOCS + PAGES)
def test_japanese_style(path):
    p = ROOT / path
    text = page_text(p) if path.endswith(".html") else prose(p.read_text(encoding="utf-8"))
    if path.endswith("文章の書き方.md"):          # 書かない例を並べている表と、4章の見出しの例は除く
        text = "\n".join(l for l in text.split("\n") if not l.startswith("|") and "ダッシュ（—）" not in l and "★など" not in l and "ダッシュと★" not in l
                         and "「なので」" not in l)
    found = []
    for i, line in enumerate(text.split("\n"), 1):
        for pat, fix in BAD:
            for m in re.finditer(pat, line):
                found.append(f"{path}: 「{line.strip()[:60]}」 の {m.group(0)} → {fix}")
    assert not found, "\n" + "\n".join(found[:60]) + (f"\n…ほか {len(found) - 60} 件" if len(found) > 60 else "")
