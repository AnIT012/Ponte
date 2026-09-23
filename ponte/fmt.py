"""整形（誰が書いても同じ見た目にする）。

  python -m ponte fmt spec/hub_app.ponte          # 書き換える
  python -m ponte fmt spec/hub_app.ponte --check  # 整形が要るかだけ見る（要るなら終了コード1）

- 字下げは1段2つの空白。見出しの間は空行1つ。行末の空白は消す。
- 同じ塊の中の節（in / out / example ... や 項目の 名前 型）は、値の位置を縦に揃える。1つだけでも空白2つ。
- who は表のように、役割・動詞・thing の列を揃える。
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


def _is_one_of(n: Node) -> bool:
    return n.keyword == "one" and n.text.startswith("of ")


def dwidth(s: str) -> int:
    """画面での幅（全角は2）"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def pad(s: str, w: int) -> str:
    return s + " " * max(0, w - dwidth(s))


def format_source(src: str) -> str:
    if re.search(r"^do\s*$", src, re.M):             # action の中身だけのファイル: 仮の action に包んで整形し、外す
        return _format_body_only(src)
    spec = parse(src)
    depth = _depths(spec)
    lines = src.splitlines()
    # 並べ方: 同じ親の子の、揃える幅
    widths: dict[int, int] = {}
    arm_widths: dict[int, int] = {}
    who_widths: dict[int, tuple] = {}
    forced: dict[int, int] = {}
    eq_widths: dict[int, int] = {}                    # do の = の位置                       # example の中の箱の中身は、example ごとに1つの幅
    for d, n in depth.values():
        kids = [c for c in n.children if not c.children or c.keyword in ("how", "example", "do", "given", "taps", "expect", "adds", "at", "says", "gets")]
        if n.is_decl and n.keyword in ("flow", "relate"):     # 矢印や関係の行は、節ではないので揃えない
            continue
        simple = [c for c in kids if not _is_arm(c) and c.text and not c.text.startswith(("[", "=")) and not c.is_decl and not _is_one_of(c)]
        if simple and not (n.is_decl and n.keyword == "who"):   # 1つだけの塊も、名前と値の間は空白2つ以上
            widths[id(n)] = max(dwidth(c.keyword) for c in simple)
        if n.is_decl and n.keyword == "who":                     # who は表のように列を揃える
            rows = [c.raw.split(None, 4) for c in n.children if len(c.raw.split()) >= 4 and c.raw.split()[1] == "can"]
            if rows:
                who_widths[id(n)] = (max(len(r[0]) for r in rows), max(len(r[2]) for r in rows), max(len(r[3]) for r in rows))
        if n.keyword == "example" and not n.is_decl:        # 1つの example の中の「箱の中身」は、まとめて同じ位置に揃える
            recs = [g for c in n.children for g in c.children if g.text and not g.children]
            if recs:
                w = max(dwidth(g.keyword) for g in recs)
                for c in n.children:
                    if c.children:
                        forced[id(c)] = w
        if n.keyword == "do" and not n.is_decl:          # do の中の「名前 = 式」は = の位置を揃える（枝を持つ行で区切る）
            run: list = []
            for c in n.children + [None]:
                if c is not None and "=" in c.raw and not c.children and not _is_arm(c):
                    run.append(c)
                    continue
                if len(run) >= 2:
                    w = max(dwidth(x.raw.split("=", 1)[0].strip()) for x in run)
                    for x in run:
                        eq_widths[id(x)] = w
                run = []
        arms = [c for c in n.children if _is_arm(c)]
        if arms:
            arm_widths[id(n)] = max(dwidth(c.raw.split("->", 1)[0].strip()) for c in arms)
    widths.update(forced)
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
        if id(n) in eq_widths:
            left, right = n.raw.split("=", 1)
            body = f"{pad(left.strip(), eq_widths[id(n)])} = {right.strip()}"
        elif p is not None and id(p) in who_widths and len(n.raw.split()) >= 4 and n.raw.split()[1] == "can":
            wr, wv, wt = who_widths[id(p)]
            parts = n.raw.split(None, 4)
            rest = parts[4] if len(parts) > 4 else ""
            body = f"{parts[0].ljust(wr)}  can {parts[2].ljust(wv)}  " + (f"{parts[3].ljust(wt)}  {rest}" if rest else parts[3])
        elif _is_one_of(n):                                   # shape の `one of "a" "b"` は2語で1つの言葉。間を開けない
            body = f"one {n.text}"
        elif _is_arm(n) and p is not None and id(p) in arm_widths:
            left, right = [x.strip() for x in n.raw.split("->", 1)]
            body = f"{pad(left, arm_widths[id(p)])} -> {right}"
        elif p is not None and id(p) in widths and n.text and not n.text.startswith(("[", "=")) and not _is_arm(n):
            body = f"{pad(n.keyword, widths[id(p)])}  {n.text}"
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


_WRAP = "action __body__"


def _format_body_only(src: str) -> str:
    """行頭の do の塊を仮の action の中へ字下げして整形し、元の形に戻す"""
    lines, out, inside = src.splitlines(), [], False
    for l in lines:
        if re.fullmatch(r"do\s*", l):
            out += [_WRAP, "  do"]
            inside = True
        elif inside and l and not l.startswith((" ", "#")):
            inside = False
            out.append(l)
        else:
            out.append(("  " + l) if inside and l.strip() else l)
    done = format_source("\n".join(out) + "\n")
    res, inside = [], False
    for l in done.splitlines():
        if l == _WRAP:
            inside = True
            continue
        if inside and l and not l.startswith(" "):
            inside = False
        res.append(l[2:] if inside and l.startswith("  ") else l)
    return "\n".join(res) + "\n"
