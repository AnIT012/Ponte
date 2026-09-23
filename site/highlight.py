"""Ponte のコードに色を付ける（仕様書14章の色分けに合わせる。ホームページ用）。

  見出し(head) 節(clause) 守り(guard) 型(type) 名前(name) 値(val) 項目(field) 記号(op) コメント(c) 止めるコメント(block)
"""
import html
import re

HEAD = "thing flow list match rule relate action group tbd scene look part style input words who change connect use".split()
CLAUSE = ("of where sort when do why in out example by ask how given at says taps gets expect adds "
          "title sub mark button lead heading empty search take top main side bottom over").split()
GUARD = "never else tbd gone limit confirm".split()
TYPES = "text number count money percent date monthday duration file image pdf".split()
TOKEN = re.compile(r'"[^"]*"|->|\||>|\[|\]|\d+(?:[:/.]\d+)*(?:\s+(?:days?|hours?|minutes?|seconds?|weeks?))?|[A-Za-z_][\w-]*|\s+|.')


def _span(cls, text):
    return f'<span class="{cls}">{html.escape(text, quote=False)}</span>'


def line(src: str, in_fields: bool, states: frozenset = frozenset()) -> str:
    if src.lstrip().startswith("##"):
        return _span("block", src)
    code, _, comment = src.partition(" #") if " #" in src and '"' not in src.split(" #")[0][-1:] else (src, "", "")
    if src.lstrip().startswith("#"):
        return _span("c", src)
    out, first, guard_bracket = [], True, False
    indented = src[:1] == " "
    for m in TOKEN.finditer(code):
        t = m.group(0)
        if t.isspace():
            out.append(t)
            continue
        if first and not indented and t in HEAD:
            cls = "guard" if t in GUARD else "head"
        elif first and indented and t in GUARD:
            cls = "guard"
        elif first and indented and in_fields and re.fullmatch(r"[a-z_]\w*", t):
            cls = "field"                          # thing / input の中の行頭は項目名（title なども）
        elif first and indented and t in CLAUSE:
            cls = "clause"
        elif t == "[" and out and out[-1].endswith(">gone</span>"):
            cls, guard_bracket = "guard", True     # gone[remove too] の中身も守り
        elif guard_bracket:
            cls = "guard"
            guard_bracket = t != "]"
        elif t in GUARD or t == ">":
            cls = "guard"
        elif t in ("[", "]", "->", "|"):
            cls = "op"
        elif t in states:
            cls = "val"                            # 状態の名前は値の仲間
        elif t in TYPES:
            cls = "type"
        elif t.startswith('"') or re.match(r"\d", t):
            cls = "val"
        elif re.fullmatch(r"[A-Z]\w*", t):
            cls = "name"
        else:
            cls = None
        out.append(_span(cls, t) if cls else html.escape(t, quote=False))
        first = False
    if comment:
        out.append(_span("c", " #" + comment))
    return "".join(out)


def states_in(src: str) -> frozenset:
    """[a | b] と flow の行から、状態の名前を集める"""
    names = set()
    for m in re.finditer(r"\w+\[([^\]]*)\]", src):
        if not m.group(0).startswith("gone["):
            names |= {x.strip() for x in m.group(1).split("|")}
    for l in re.findall(r"^\s+(\w.*->.*)$", src, re.M):
        names |= set(re.findall(r"[a-z_]\w*", l))
    return frozenset(names)


def highlight(src: str, states: frozenset | None = None) -> str:
    states = states_in(src) if states is None else states
    rows, in_fields = [], False
    for l in src.rstrip("\n").split("\n"):
        if l and l[0] != " " and not l.startswith("#"):
            in_fields = l.split()[0] in ("thing", "input")
        rows.append(line(l, in_fields, states))
    return "\n".join(rows)
