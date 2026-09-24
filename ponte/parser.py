"""パーサー（仕様 v0.2）。

行ベース。行頭（字下げ無し）が「見出し」、字下げした行が「節」。
節はさらに字下げして子を持てる（how の中身、example の中身、match の枝など）。
group の中だけは、字下げした所に見出しを書ける。

コメントは2種類:
  #   普通のコメント。捨てる
  ##  止めるコメント。Spec.blocking に行番号と中身を残す（チェッカーが E06 で止める）

木にするだけで、意味付けは checker がする。よく使う読み取りだけここに置く。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

DECLARATIONS = (
    "thing", "flow", "list", "match", "rule", "relate", "action", "group",
    "tbd", "never", "scene", "look", "part", "style", "input", "words",
    "who", "change", "connect", "shape", "use", "model", "job",
)


class ParseError(Exception):
    def __init__(self, line: int, message: str):
        super().__init__(f"L{line}: {message}")
        self.line = line
        self.message = message


@dataclass
class Node:
    keyword: str
    text: str
    raw: str
    line: int
    indent: int
    children: list["Node"] = field(default_factory=list)
    is_decl: bool = False
    blocking: str | None = None   # 行の後ろに ## があれば、その中身
    parent: "Node | None" = field(default=None, repr=False, compare=False)

    def child(self, keyword: str) -> "Node | None":
        for c in self.children:
            if c.keyword == keyword:
                return c
        return None

    def children_of(self, keyword: str) -> list["Node"]:
        return [c for c in self.children if c.keyword == keyword]

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    @property
    def name(self) -> str:
        return self.text.split()[0] if self.text else ""


@dataclass
class Spec:
    path: str
    roots: list[Node]
    lines: list[str]
    blocking: list[tuple[int, str]]   # (行番号, ## の後ろ)。行まるごと ## のもの
    line_map: list = field(default_factory=list)   # use で取り込んだ時の (始まりの行, ファイル, ずらした数)

    def where(self, line: int) -> tuple[str, int]:
        """行番号 → (ファイル, そのファイルでの行)"""
        best = (1, self.path, 0)
        for start, f, off in self.line_map or [(1, self.path, 0)]:
            if start <= line and start >= best[0]:
                best = (start, f, off)
        return best[1], line - best[2]

    def walk(self):
        for r in self.roots:
            yield from r.walk()

    def decls(self, keyword: str | None = None) -> list[Node]:
        """見出し（group の中のものも含む）。"""
        return [n for n in self.walk() if n.is_decl and (keyword is None or n.keyword == keyword)]

    def find(self, keyword: str, name: str) -> Node | None:
        for d in self.decls(keyword):
            if d.name == name:
                return d
        return None


# ---------------------------------------------------------------------------
# 行
# ---------------------------------------------------------------------------

def split_comment(line: str) -> tuple[str, str | None, bool]:
    """(コード, コメント, 止めるコメントか)。引用符の中の # は無視。"""
    in_quote = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quote = not in_quote
        elif ch == "#" and not in_quote:
            if re.match(r"#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})(?![\w])", line[i:]) and (i == 0 or line[i - 1] in " ,("):
                continue   # #4F46E5 は色の値（コメントではない）
            blocking = line[i:i + 2] == "##"
            rest = line[i + (2 if blocking else 1):].strip()
            return line[:i].rstrip(), rest, blocking
    return line.rstrip(), None, False


def parse_line(line: str, lineno: int, blocking_out: list) -> Node | None:
    lead = line[: len(line) - len(line.lstrip())]
    if "\t" in lead:
        raise ParseError(lineno, "字下げにタブは使えません（スペースで）")
    code, comment, blocking = split_comment(line)
    stripped = code.strip()
    if not stripped:
        if blocking:
            blocking_out.append((lineno, comment or ""))
        return None
    indent = len(code) - len(code.lstrip(" "))
    parts = stripped.split(None, 1)
    kw = parts[0]
    text = parts[1].strip() if len(parts) > 1 else ""
    # 状態の宣言 `status[a | b]` は keyword を名前にする
    m = re.match(r"^(\w[\w-]*)\[", stripped)
    if m:
        kw = m.group(1)
        text = stripped[len(kw):]
    return Node(keyword=kw, text=text, raw=stripped, line=lineno, indent=indent,
                blocking=(comment if blocking else None))


# ---------------------------------------------------------------------------
# 木
# ---------------------------------------------------------------------------

def parse(source: str, path: str = "<string>") -> Spec:
    lines = source.splitlines()
    roots: list[Node] = []
    blocking: list[tuple[int, str]] = []
    stack: list[Node] = []

    for i, line in enumerate(lines, start=1):
        node = parse_line(line, i, blocking)
        if node is None:
            continue

        if node.indent == 0:
            if node.keyword not in DECLARATIONS:
                import difflib
                near = difflib.get_close_matches(node.keyword, sorted(DECLARATIONS), n=1, cutoff=0.6)
                hint = f"。もしかして `{near[0]}`？" if near else f"（{' / '.join(sorted(DECLARATIONS))}）"
                raise ParseError(i, f"行頭に書けるのは見出しだけです: '{node.raw}'{hint}")
            node.is_decl = True
            roots.append(node)
            stack = [node]
            continue

        if not stack:
            raise ParseError(i, f"見出しの前に字下げした行があります: '{node.raw}'")
        while stack and stack[-1].indent >= node.indent:
            stack.pop()
        if not stack:
            raise ParseError(i, f"字下げが合いません: '{node.raw}'")
        parent = stack[-1]
        if parent.children and parent.children[0].indent != node.indent:
            raise ParseError(
                i, f"同じ塊の中で字下げが揃っていません（{parent.children[0].indent} と {node.indent}）: '{node.raw}'")
        # group の直下は見出し
        if parent.is_decl and parent.keyword == "group" and node.keyword in DECLARATIONS:
            node.is_decl = True
        node.parent = parent
        parent.children.append(node)
        stack.append(node)

    return Spec(path=path, roots=roots, lines=lines, blocking=blocking)


STD_DIR = os.path.join(os.path.dirname(__file__), "std")   # use std/名前 で読む標準ライブラリ


def parse_file(path: str, _seen: set | None = None, text: str | None = None) -> Spec:
    """ファイルを読む。`use "other.ponte"` があれば、その見出しも取り込む（同じ場所からの相対パス）。
    取り込んだ行は元のファイルの後ろに続けた行番号になり、Spec.where(行) で元のファイルと行に戻せる。
    text を渡すと、ファイルの代わりにそれを読む（エディタで書きかけの中身。use はファイルから）。"""
    seen = _seen if _seen is not None else set()
    seen.add(os.path.abspath(path))
    if text is None:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    spec = parse(text, path)
    spec.line_map = [(1, path, 0)]
    for u in [d for d in spec.roots if d.keyword == "use"]:
        m = re.match(r'^"([^"]+)"$', u.text.strip())
        ms = re.match(r"^std/(\w+)$", u.text.strip())       # 標準ライブラリ（言語についてくる .ponte）
        if ms:
            other = os.path.join(STD_DIR, ms.group(1) + ".ponte")
            if not os.path.exists(other):
                have = sorted(f[:-len(".ponte")] for f in os.listdir(STD_DIR) if f.endswith(".ponte"))
                raise ParseError(u.line, f"std/{ms.group(1)} はありません（あるのは {', '.join('std/' + h for h in have)}）")
        elif not m:
            raise ParseError(u.line, f'use は `use "ファイル.ponte"` か `use std/名前` で書きます: {u.raw!r}')
        else:
            other = os.path.join(os.path.dirname(path), m.group(1))
        if os.path.abspath(other) in seen:
            continue
        if not os.path.exists(other):
            raise ParseError(u.line, f"use のファイルがありません: {m.group(1)}")
        sub = parse_file(other, seen)
        offset = len(spec.lines)
        for n in sub.walk():
            n.line += offset
        spec.roots += sub.roots
        spec.blocking += [(ln + offset, t) for ln, t in sub.blocking]
        spec.line_map += [(start + offset, f, off + offset) for start, f, off in sub.line_map]
        spec.lines += sub.lines
    return spec


# ---------------------------------------------------------------------------
# よく使う読み取り
# ---------------------------------------------------------------------------

def states_of(text: str) -> list[str] | None:
    """`[a | b | c]`（先頭が [ の文字列）→ [a, b, c]"""
    m = re.match(r"^\[([^\]]*)\]", text.strip())
    if not m:
        return None
    return [s.strip() for s in m.group(1).split("|") if s.strip()]


@dataclass
class Field:
    name: str
    type: str                  # "text" / "User" / "list of User" / "state"
    states: list[str] | None
    gone: str | None           # gone[...] の中身
    line: int


GONE = re.compile(r"\bgone\[([^\]]*)\]")


def thing_fields(thing: Node) -> list[Field]:
    out = []
    for c in thing.children:
        if c.text.startswith("["):
            st = states_of(c.text)
            out.append(Field(c.keyword, "state", st, None, c.line))
            continue
        rest = c.text
        gone = None
        m = GONE.search(rest)
        if m:
            gone = m.group(1).strip()
            rest = (rest[:m.start()] + rest[m.end():]).strip()
        if not rest:
            raise ParseError(c.line, f"項目は `名前 型` で書きます: '{c.raw}'")
        out.append(Field(c.keyword, rest.split(",")[0].strip(), None, gone, c.line))
    return out


def flow_parts(flow: Node) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(遷移, 勝ち)。`a -> b | c` と `x > y`"""
    edges, wins = [], []
    for c in flow.children:
        if "->" in c.raw:
            steps = [s.strip() for s in c.raw.split("->")]
            for src, dst in zip(steps, steps[1:]):
                for s in [x.strip() for x in src.split("|")]:
                    for d in [x.strip() for x in dst.split("|")]:
                        edges.append((s, d))
        elif re.fullmatch(r"\w+\s*>\s*\w+", c.raw):
            a, b = [x.strip() for x in c.raw.split(">")]
            wins.append((a, b))
        else:
            raise ParseError(c.line, f"flow の中は `a -> b` か `a > b` で書きます: '{c.raw}'")
    return edges, wins


def flow_states(flow: Node) -> list[str]:
    seen: list[str] = []
    for s, d in flow_parts(flow)[0]:
        for x in (s, d):
            if x not in seen:
                seen.append(x)
    return seen


RELATE = re.compile(r"^(\S+)\s+(then no|then|before|>|else)\s+(\S+)$")


def relate_lines(spec: Spec) -> list[tuple[str, str, str, int]]:
    """全部の relate の行 → (A, 関係, B, 行番号)"""
    out = []
    for r in spec.decls("relate"):
        for c in r.children:
            m = RELATE.match(c.raw)
            if not m:
                raise ParseError(c.line, f"relate の行は `A then B` / `A then no B` / `A before B` / `A > B` / `A else B`: '{c.raw}'")
            out.append((m.group(1), m.group(2), m.group(3), c.line))
    return out


def match_arms(node: Node) -> list[tuple[list[str], str, Node]]:
    """match の枝 → ([左の値...], 右, 行)"""
    arms = []
    for c in node.children:
        if "->" not in c.raw:
            continue
        left, right = [s.strip() for s in c.raw.split("->", 1)]
        arms.append(([x.strip() for x in left.split("|")], right, c))
    return arms


def words_entries(words: Node) -> dict[str, str]:
    """words の中身 → {鍵: 訳}。鍵は名前か "引用符の文"（spec にそのまま書いた日本語など）"""
    out = {}
    for c in words.children:
        m = re.match(r'^"([^"]+)"\s+(.+)$', c.raw) or re.match(r"^(\S+)\s+(.+)$", c.raw)
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"')
    return out


BUTTON_OPTS = ("named", "toggle", "set", "icon", "confirm", "tone")
TONES = ("main", "quiet", "good", "danger")


def parse_button(text: str) -> dict | None:
    """`submitted-button named 提出した icon send confirm "提出しますか？"` → 辞書"""
    toks = re.findall(r'"[^"]*"|\S+', text.strip())
    if not toks:
        return None
    b = {"id": toks[0], "label": None, "act": None, "icon": None, "confirm": None, "tone": None}
    i = 1
    while i < len(toks):
        t = toks[i]
        if t == "named" and i + 1 < len(toks):
            b["label"] = toks[i + 1].strip('"')     # 空白を含む名前は "引用符" で書く
            i += 2
        elif t == "toggle" and i + 1 < len(toks):
            b["act"] = {"kind": "toggle", "state": toks[i + 1]}
            i += 2
        elif t == "set" and i + 2 < len(toks):
            b["act"] = {"kind": "set", "state": toks[i + 1], "value": toks[i + 2]}
            i += 3
        elif t == "icon" and i + 1 < len(toks):
            b["icon"] = toks[i + 1]
            i += 2
        elif t == "tone" and i + 1 < len(toks) and toks[i + 1] in TONES:
            b["tone"] = toks[i + 1]
            i += 2
        elif t == "confirm" and i + 1 < len(toks):
            b["confirm"] = toks[i + 1].strip('"')
            i += 2
        else:
            return None
    return b
