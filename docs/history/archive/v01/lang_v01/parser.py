"""パーサー。

.spec は行ベース。行頭（字下げ無し）が「宣言」、字下げした行が「節」。
節はさらに字下げして子を持てる（how の中身、rule の example の中身など）。
文法の意味付けはここではしない。木にするだけ。意味は checker / codegen が見る。

木の形:
    Node(keyword, text, line, indent, children, comment, proposed)
      keyword : 行の最初の語（"entity", "where", "draft", "owner:" ...）
      text    : keyword の後ろの残り（両端の空白を除いたもの）
      raw     : コメントを外した行そのもの（両端の空白を除いたもの）
"""
from __future__ import annotations

from dataclasses import dataclass, field

DECLARATIONS = (
    "entity", "flow", "list", "match", "rule", "action",
    "connect", "role",      # △ 提案。パースはするが意味は付けない
    "unknown", "never", "derive",
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
    comment: str = ""
    proposed: bool = False
    parent: "Node | None" = field(default=None, repr=False, compare=False)

    # --- 便利関数 -------------------------------------------------------
    def child(self, keyword: str) -> "Node | None":
        """keyword が一致する最初の子。無ければ None。"""
        for c in self.children:
            if c.keyword == keyword:
                return c
        return None

    def children_of(self, keyword: str) -> list["Node"]:
        return [c for c in self.children if c.keyword == keyword]

    def walk(self):
        """自分と子孫を上から順に。"""
        yield self
        for c in self.children:
            yield from c.walk()

    @property
    def head(self) -> str:
        """`keyword text` の形（表示用）。"""
        return f"{self.keyword} {self.text}".strip()

    @property
    def name(self) -> str:
        """宣言の名前。`entity Application` なら Application。"""
        return self.text.split()[0] if self.text else ""


@dataclass
class Spec:
    path: str
    decls: list[Node]
    lines: list[str]

    def decls_of(self, keyword: str) -> list[Node]:
        return [d for d in self.decls if d.keyword == keyword]

    def find(self, keyword: str, name: str) -> Node | None:
        for d in self.decls_of(keyword):
            if d.name == name:
                return d
        return None

    def walk(self):
        for d in self.decls:
            yield from d.walk()


# ---------------------------------------------------------------------------
# 行の分解
# ---------------------------------------------------------------------------

def split_comment(line: str) -> tuple[str, str]:
    """`code  # comment` を (code, comment) に分ける。引用符の中の # は無視。"""
    in_quote = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quote = not in_quote
        elif ch == "#" and not in_quote:
            return line[:i].rstrip(), line[i + 1:].strip()
    return line.rstrip(), ""


def parse_line(line: str, lineno: int) -> Node | None:
    """1行を Node にする。空行・コメントだけの行は None。"""
    if "\t" in line[: len(line) - len(line.lstrip())]:
        raise ParseError(lineno, "字下げにタブは使えません（スペースで）")
    code, comment = split_comment(line)
    stripped = code.strip()
    if not stripped:
        return None
    indent = len(code) - len(code.lstrip(" "))
    parts = stripped.split(None, 1)
    keyword = parts[0]
    text = parts[1].strip() if len(parts) > 1 else ""
    # 「sort by」「on conflict」は2語で1つの節
    for two in ("sort by", "on conflict", "on failure"):
        if stripped.startswith(two + " ") or stripped == two:
            keyword = two
            text = stripped[len(two):].strip()
    return Node(
        keyword=keyword, text=text, raw=stripped, line=lineno, indent=indent,
        comment=comment, proposed=("proposed" in comment.lower()),
    )


# ---------------------------------------------------------------------------
# 木の組み立て
# ---------------------------------------------------------------------------

def parse(source: str, path: str = "<string>") -> Spec:
    lines = source.splitlines()
    decls: list[Node] = []
    stack: list[Node] = []  # 字下げの浅い順に、いま開いている親たち

    for i, line in enumerate(lines, start=1):
        node = parse_line(line, i)
        if node is None:
            continue

        if node.indent == 0:
            if node.keyword not in DECLARATIONS:
                raise ParseError(
                    i, f"行頭に書けるのは宣言だけです（{', '.join(DECLARATIONS)}）: '{node.raw}'"
                )
            decls.append(node)
            stack = [node]
            continue

        if not stack:
            raise ParseError(i, f"宣言の前に字下げした行があります: '{node.raw}'")

        # 自分より浅いか同じ字下げの親を閉じる
        while stack and stack[-1].indent >= node.indent:
            stack.pop()
        if not stack:
            raise ParseError(i, f"字下げが合いません: '{node.raw}'")
        parent = stack[-1]
        # 親の子は全部同じ字下げでなければならない
        if parent.children and parent.children[0].indent != node.indent:
            raise ParseError(
                i, f"同じ塊の中で字下げが揃っていません（{parent.children[0].indent} と {node.indent}）: '{node.raw}'"
            )
        node.parent = parent
        parent.children.append(node)
        stack.append(node)

    return Spec(path=path, decls=decls, lines=lines)


def parse_file(path: str) -> Spec:
    with open(path, encoding="utf-8") as f:
        return parse(f.read(), path)


# ---------------------------------------------------------------------------
# よく使う読み取り（意味付けの最小限。checker と codegen が共有する）
# ---------------------------------------------------------------------------

def flow_target(flow: Node) -> tuple[str, str]:
    """`flow Application.status` → ("Application", "status")"""
    name = flow.name
    if "." not in name:
        raise ParseError(flow.line, f"flow は 箱名.項目名 で書きます: '{flow.raw}'")
    entity, fld = name.split(".", 1)
    return entity, fld


def flow_transitions(flow: Node) -> list[tuple[str, str]]:
    """`draft -> submitted -> passed | failed` → [(draft,submitted),(submitted,passed),(submitted,failed)]"""
    edges: list[tuple[str, str]] = []
    for c in flow.children:
        if c.keyword == "on conflict" or "->" not in c.raw:
            continue
        steps = [s.strip() for s in c.raw.split("->")]
        for src, dst in zip(steps, steps[1:]):
            for s in [x.strip() for x in src.split("|")]:
                for d in [x.strip() for x in dst.split("|")]:
                    edges.append((s, d))
    return edges


def flow_states(flow: Node) -> list[str]:
    """出てくる順に状態名。"""
    seen: list[str] = []
    for s, d in flow_transitions(flow):
        for x in (s, d):
            if x not in seen:
                seen.append(x)
    return seen


def flow_conflicts(flow: Node) -> list[tuple[str, str]]:
    """`on conflict failed wins over passed` → [("failed", "passed")]  (勝者, 敗者)"""
    out = []
    for c in flow.children_of("on conflict"):
        words = c.text.split()
        if len(words) == 4 and words[1] == "wins" and words[2] == "over":
            out.append((words[0], words[3]))
        else:
            raise ParseError(c.line, f"on conflict は `A wins over B` で書きます: '{c.raw}'")
    return out


def entity_fields(entity: Node) -> list[tuple[str, str, int]]:
    """`owner: ref User` → [("owner", "ref User", line)]"""
    out = []
    for c in entity.children:
        if c.keyword.endswith(":"):
            out.append((c.keyword[:-1], c.text, c.line))
        elif c.keyword == "derive":
            continue
        else:
            raise ParseError(c.line, f"entity の項目は `名前: 型` で書きます: '{c.raw}'")
    return out


def one_of_values(typ: str) -> list[str] | None:
    """`one of [a, b, c]` → [a, b, c]。違う型なら None。"""
    t = typ.strip()
    if t.startswith("one of [") and t.endswith("]"):
        return [v.strip() for v in t[len("one of ["):-1].split(",") if v.strip()]
    return None
