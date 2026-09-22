"""action の中身（do）と shape を動かす（仕様 v0.2 5章 action / 10章 道具）。

do に書けるのは `名前 = 式` と、名前を付けた match だけ。
- 順番は名前の依存関係で決まる（上から順ではない）。
- 答えは「他のどの行からも使われていない行」。ちょうど1つでなければエラー（QUESTIONS_v0.2 A1）。
- ループ・再帰・書き換えは無いので、必ず止まる。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .parser import Node, match_arms, states_of


class BodyError(Exception):
    def __init__(self, line: int, message: str):
        super().__init__(f"L{line}: {message}")
        self.line = line
        self.message = message


@dataclass(frozen=True)
class Tagged:
    """状態の付いた値。`found 10/15 12:00` や `missing`"""
    state: str
    value: object = None

    def __str__(self):
        return self.state if self.value is None else f"{self.state} {self.value}"


# ---------------------------------------------------------------------------
# shape（正規表現の代わり）
# ---------------------------------------------------------------------------

_TOK = re.compile(r'"[^"]*"|\S+')


def _range(tok: str) -> str:
    m = re.fullmatch(r"(\d+)\.\.(\d+)", tok)
    if m:
        return "{%s,%s}" % (m.group(1), m.group(2))
    if tok.isdigit():
        return "{%s}" % tok
    raise ValueError(tok)


def _elements(tokens: list[str], line: int) -> str:
    out, i = "", 0
    classes = {"digits": r"\d", "any": r".", "letters": r"[^\W\d_]", "word": r"\w"}
    while i < len(tokens):
        t = tokens[i]
        if t.startswith('"'):
            out += re.escape(t[1:-1])
            i += 1
        elif t == "space":
            out += r"\s+"
            i += 1
        elif t in classes:
            try:
                out += classes[t] + _range(tokens[i + 1])
            except (IndexError, ValueError):
                raise BodyError(line, f"shape: {t} の後ろに数か範囲（1..2）が要ります")
            i += 2
        elif re.fullmatch(r"[a-z_]\w*", t) and i + 1 < len(tokens) and tokens[i + 1] in classes:
            name, cls = t, tokens[i + 1]
            try:
                out += f"(?P<{name}>{classes[cls]}{_range(tokens[i + 2])})"
            except (IndexError, ValueError):
                raise BodyError(line, f"shape: {name} {cls} の後ろに数か範囲（1..2）が要ります")
            i += 3
        else:
            raise BodyError(line, f"shape の書き方が分かりません: '{t}'（使えるのは \"文字\" / space / digits / letters / any / word / maybe）")
    return out


def compile_shape(shape: Node) -> re.Pattern:
    pat = ""
    for c in shape.children:
        toks = _TOK.findall(c.raw)
        if toks and toks[0] == "maybe":
            rest = toks[1:]
            inner = _elements(rest, c.line) if rest != ["space"] else r"\s"
            pat += f"(?:{inner})?" if rest != ["space"] else r"\s*"
        else:
            pat += _elements(toks, c.line)
    try:
        return re.compile(pat)
    except re.error as e:
        raise BodyError(shape.line, f"shape {shape.name}: {e}")


# ---------------------------------------------------------------------------
# 式
# ---------------------------------------------------------------------------

def in_range(key, text: str) -> bool:
    """match の左の `1..3` / `..-1` / `4..`（数の範囲。両端を含む）"""
    m = re.fullmatch(r"(-?\d+)?\.\.(-?\d+)?", text)
    if not m or not isinstance(key, int) or (m.group(1) is None and m.group(2) is None):
        return False
    lo = int(m.group(1)) if m.group(1) is not None else None
    hi = int(m.group(2)) if m.group(2) is not None else None
    return (lo is None or key >= lo) and (hi is None or key <= hi)

@dataclass
class Step:
    name: str
    expr: str
    node: Node
    states: list[str] | None        # `kind[a | b] = ...` の宣言


class Body:
    def __init__(self, do: Node, shapes: dict[str, Node], inputs: list[str], out_states: dict[str, bool],
                 single_result: bool = True, lines: list[Node] | None = None):
        """out_states: out の状態名 → 値を持つか（found monthday なら True、missing なら False）"""
        self.shapes = {n: compile_shape(s) for n, s in shapes.items()}
        self.inputs = inputs
        self.out_states = out_states
        self.steps: dict[str, Step] = {}
        for c in (lines if lines is not None else do.children):
            m = re.match(r"^(\w+)\s*(\[[^\]]*\])?\s*=\s*(.+)$", c.raw)
            if not m:
                raise BodyError(c.line, f"do に書けるのは `名前 = 式` だけです: '{c.raw}'")
            name = m.group(1)
            if name in self.steps or name in inputs:
                raise BodyError(c.line, f"{name} はもう使われています（書き換えはできません）")
            self.steps[name] = Step(name, m.group(3).strip(), c, states_of(m.group(2)) if m.group(2) else None)
        if not self.steps and single_result:
            raise BodyError(do.line, "do が空です")
        self.result = None
        if not single_result:
            return
        def refs(expr: str) -> set:
            words = re.findall(r"\b\w+\b", re.sub(r'"[^"]*"', "", expr))
            if words and words[0] in out_states:     # 先頭の状態名は値の印で、名前の参照ではない
                words = words[1:]
            return set(words)
        used = set()
        for s in self.steps.values():
            used |= refs(s.expr)
            for _, r, _ in match_arms(s.node):
                used |= refs(r)
        sinks = [n for n in self.steps if n not in used]
        if len(sinks) != 1:
            raise BodyError(do.line, f"答えの行（どこからも使われていない行）がちょうど1つではありません: {sinks or 'なし（一周している）'}")
        self.result = sinks[0]

    def run(self, inputs: dict) -> object:
        memo: dict = dict(inputs)
        return self._get(self.result, memo, [])

    def values(self, inputs: dict) -> dict:
        """全部の行の値（part で使う）"""
        memo: dict = dict(inputs)
        for n in self.steps:
            self._get(n, memo, [])
        return memo

    # --------------------------------------------------------------
    def _get(self, name: str, memo: dict, path: list):
        if name in memo:
            return memo[name]
        if name not in self.steps:
            raise KeyError(name)
        if name in path:
            raise BodyError(self.steps[name].node.line, f"一周しています: {' -> '.join(path + [name])}")
        st = self.steps[name]
        if st.expr.startswith("match "):
            v = self._match(st, memo, path + [name])
        else:
            v = self._eval(st.expr, st, memo, path + [name])
        if st.states is not None:
            tag = v.state if isinstance(v, Tagged) else v
            if tag not in st.states:
                raise BodyError(st.node.line, f"{name} は {' | '.join(st.states)} のどれかのはずが {tag}")
        memo[name] = v
        return v

    def _match(self, st: Step, memo, path):
        subject = self._eval(st.expr[len("match "):], st, memo, path)
        key = subject.state if isinstance(subject, Tagged) else subject
        chosen = None
        for lefts, right, arm in match_arms(st.node):
            if "else" in lefts:
                chosen = chosen or (right, arm)
                continue
            for l in lefts:
                if str(key) == l or (re.fullmatch(r"-?\d+", l) and isinstance(key, int) and key == int(l)) or in_range(key, l):
                    return self._eval(right, st, memo, path, arm.line)
        if chosen is None:
            raise BodyError(st.node.line, f"match {st.expr[6:]}: {key} に当たる枝がありません")
        return self._eval(chosen[0], st, memo, path, chosen[1].line)

    def _eval(self, expr: str, st: Step, memo, path, line: int | None = None):
        e = expr.strip()
        line = line or st.node.line
        ev = lambda x: self._eval(x, st, memo, path, line)
        if re.fullmatch(r'"[^"]*"', e):
            return e[1:-1]
        if re.fullmatch(r"-?\d+", e):
            return int(e)
        # 状態（out の状態 / 自分で宣言した状態）
        head, _, rest = e.partition(" ")
        if head in self.out_states:
            if self.out_states[head]:
                if not rest:
                    raise BodyError(line, f"{head} には値が要ります（例: {head} monthday of first of hits）")
                return Tagged(head, ev(rest))
            if rest:
                raise BodyError(line, f"{head} は値を持ちません")
            return Tagged(head)
        if not rest and st.states and e in st.states:
            return e
        if not rest and any(e in (s.states or []) for s in self.steps.values()):
            return e
        # 名前
        if re.fullmatch(r"\w+", e):
            try:
                return self._get(e, memo, path)
            except KeyError:
                raise BodyError(line, f"「{e}」がどこにもありません")
        # 道具
        m = re.fullmatch(r"find all (\w+) in (.+)", e)
        if m:
            if m.group(1) not in self.shapes:
                raise BodyError(line, f"shape {m.group(1)} がありません")
            text = str(ev(m.group(2)))
            return [dict(mm.groupdict(), text=mm.group(0)) for mm in self.shapes[m.group(1)].finditer(text)]
        m = re.fullmatch(r"days until (.+)", e)
        if m:
            from .values import parse_time
            now = memo.get("__now__")
            if now is None:
                raise BodyError(line, "days until: 今の時刻がありません")
            try:
                t = parse_time(str(ev(m.group(1))), now.year)
            except ValueError as err:
                raise BodyError(line, str(err))
            return (t.date() - now.date()).days
        m = re.fullmatch(r"(count|length|first|last|monthday|number) of (.+)", e)
        if m:
            v = ev(m.group(2))
            op = m.group(1)
            if op in ("count", "length"):
                return len(v)
            if op in ("first", "last"):
                if not v:
                    raise BodyError(line, f"{op} of: 空の集まりです（先に count で分けてください）")
                return v[0] if op == "first" else v[-1]
            if op == "number":
                return int(str(v))
            if not isinstance(v, dict) or not {"month", "day"} <= set(v):
                raise BodyError(line, "monthday of: month と day を取り出した shape の結果が要ります")
            h, mi = v.get("hour"), v.get("minute")
            s = f"{int(v['month'])}/{int(v['day'])}"
            return s + (f" {int(h)}:{mi}" if h is not None and mi is not None else "")
        m = re.fullmatch(r"(normalize|trim|lower|upper) (.+)", e)
        if m:
            v = str(ev(m.group(2)))
            return {"normalize": lambda s: unicodedata.normalize("NFKC", s), "trim": str.strip,
                    "lower": str.lower, "upper": str.upper}[m.group(1)](v)
        m = re.fullmatch(r'split (.+) by "([^"]*)"', e)
        if m:
            return str(ev(m.group(1))).split(m.group(2))
        m = re.fullmatch(r'join (.+) by "([^"]*)"', e)
        if m:
            return m.group(2).join(str(x) for x in ev(m.group(1)))
        m = re.fullmatch(r'replace "([^"]*)" with "([^"]*)" in (.+)', e)
        if m:
            return str(ev(m.group(3))).replace(m.group(1), m.group(2))
        m = re.fullmatch(r"(\w+) (\+|-) (\w+)", e)
        if m:
            a, b = ev(m.group(1)), ev(m.group(3))
            return a + b if m.group(2) == "+" else a - b
        raise BodyError(line, f"式が分かりません: '{e}'（使える道具は 10章）")


# ---------------------------------------------------------------------------
# action から Body を作る
# ---------------------------------------------------------------------------

def out_states_of(action: Node) -> dict[str, bool]:
    o = action.child("out")
    alts = [a.strip().split() for a in (o.text.split("|") if o else [])]
    return {a[0]: len(a) > 1 for a in alts if a and len(a) >= 1 and not (len(a) == 1 and a[0] in ("text", "number", "monthday", "date"))}


def input_names(action: Node) -> list[str]:
    i = action.child("in")
    return [i.text.split()[0]] if i and i.text else []


def body_of(action: Node, do: Node, shapes: dict[str, Node]) -> Body:
    return Body(do, shapes, input_names(action), out_states_of(action))


def parse_expected(text: str, out_states: dict[str, bool]):
    """example の右側 → 比べる値"""
    t = text.strip()
    head, _, rest = t.partition(" ")
    if head in out_states:
        return Tagged(head, rest.strip() or None) if out_states[head] else Tagged(head)
    return t.strip('"')


def same(got, want) -> bool:
    if isinstance(want, Tagged):
        return isinstance(got, Tagged) and got.state == want.state and (want.value is None or str(got.value) == str(want.value))
    return str(got) == str(want)
