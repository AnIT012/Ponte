"""整形（誰が書いても同じ見た目にする）。

  python -m lang fmt spec/hub_app.lang          # 書き換える
  python -m lang fmt spec/hub_app.lang --check  # 整形が要るかだけ見る（要るなら終了コード1）

- 字下げは1段2つの空白。見出しの間は空行1つ。行末の空白は消す。
- 同じ塊の中の節（in / out / example ... や 項目の 名前 型）は、値の位置を縦に揃える。
- match の枝は `->` の位置を揃える。
- コメント（# と ##）は消さない。
- 整形の前と後で、読んだ意味（木）が1つでも違えば書き換えない（安全のため）。
"""
from __future__ import annotations

import re
import unicodedata

from .parser import Node, ParseError, parse, split_comment


class FormatError(Exception):
    pass


def _depths(spec) -> dict[int, tuple[int, Node]]:
    out = {}

    def walk(n: Node, d: int):
        out[n.line] = (d, n)
        for c in n.children:
            walk(c, d + 1)
    for r in spec.roots:
        walk(r, 0)
    return out


def _signature(spec) -> list:
    """意味の比べ方: 全部のノードの（深さ, keyword, 空白を詰めた text, ## の中身）と、行まるごとの ##"""
    sig = []

    def walk(n: Node, d: int):
        sig.append((d, n.keyword, re.sub(r"\s+", " ", n.text), n.blocking))
        for c in n.children:
            walk(c, d + 1)
    for r in spec.roots:
        walk(r, 0)
    return sig + [("##", t) for _, t in spec.blocking]


def _is_arm(n: Node) -> bool:
    """match の枝だけ（flow の矢印や example の -> は枝ではない）"""
    p = n.parent
    if p is None or "->" not in n.raw or n.is_decl:
        return False
    return (p.is_decl and p.keyword == "match") or bool(re.search(r"(^|\s|=)match\s", p.raw))


def dwidth(s: str) -> int:
    """画面での幅（全角は2）"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def pad(s: str, w: int) -> str:
    return s + " " * max(0, w - dwidth(s))


def format_source(src: str) -> str:
    spec = parse(src)
    depth = _depths(spec)
    lines = src.splitlines()
    # 並べ方: 同じ親の子の、揃える幅
    widths: dict[int, int] = {}
    arm_widths: dict[int, int] = {}
    for d, n in depth.values():
        kids = [c for c in n.children if not c.children or c.keyword in ("how", "example", "do")]
        if n.is_decl and n.keyword in ("flow", "relate"):     # 矢印や関係の行は、節ではないので揃えない
            continue
        simple = [c for c in kids if not _is_arm(c) and c.text and not c.text.startswith(("[", "=")) and not c.is_decl]
        if len(simple) >= 2:
            widths[id(n)] = max(len(c.keyword) for c in simple)
        arms = [c for c in n.children if _is_arm(c)]
        if arms:
            arm_widths[id(n)] = max(dwidth(c.raw.split("->", 1)[0].strip()) for c in arms)
    out: list[str] = []
    pending_comments: list[str] = []
    for i, line in enumerate(lines, start=1):
        code, comment, blocking = split_comment(line)
        tail = ""
        if comment is not None:
            tail = ("## " if blocking else "# ") + comment
        if not code.strip():
            if comment is not None:
                pending_comments.append(tail)          # コメントだけの行は、次のコードの行の字下げに合わせる
            elif pending_comments:
                if out and out[-1] != "":
                    out.append("")
                out.extend(pending_comments)            # 空行で終わるコメントの塊は、見出しにくっつけない
                pending_comments = []
                out.append("")
            elif out and out[-1] != "" and not pending_comments:
                out.append("")
            continue
        d, n = depth[i]
        ind = "  " * d
        if n.is_decl and d == 0 and out and out[-1] != "":
            out.append("")                               # 見出しの前は空行（見出しにくっついたコメントの前も）
        for c in pending_comments:
            out.append(ind + c)
        pending_comments = []
        p = n.parent
        if _is_arm(n) and p is not None and id(p) in arm_widths:
            left, right = [x.strip() for x in n.raw.split("->", 1)]
            body = f"{pad(left, arm_widths[id(p)])} -> {right}"
        elif p is not None and id(p) in widths and n.text and not n.text.startswith(("[", "=")) and not _is_arm(n):
            body = f"{n.keyword.ljust(widths[id(p)])}  {n.text}"
        elif not n.is_decl and n.text and not n.text.startswith("["):
            body = f"{n.keyword} {n.text}"             # 1つだけの節は、名前と値の間を空白1つに
        else:
            body = n.raw
        out.append((ind + body + (("  " + tail) if tail else "")).rstrip())
    for c in pending_comments:
        out.append(c)
    while out and out[-1] == "":
        out.pop()
    result = "\n".join(out) + "\n"
    try:
        after = parse(result)
    except ParseError as e:
        raise FormatError(f"整形したら読めなくなりました（{e}）。書き換えません")
    if _signature(after) != _signature(spec):
        raise FormatError("整形の前後で意味が変わってしまうので、書き換えません")
    return result
