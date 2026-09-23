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
TOKEN = re.compile(r'"[^"]*"|->|\||>|\[[^\]]*\]|\d+(?:[:/.]\d+)*(?:\s+(?:days?|hours?|minutes?|seconds?|weeks?))?|[A-Za-z_][\w-]*|\s+|.')


def _span(cls, text):
    return f'<span class="{cls}">{html.escape(text, quote=False)}</span>'


def line(src: str, in_fields: bool) -> str:
    if src.lstrip().startswith("##"):
        return _span("block", src)
    code, _, comment = src.partition(" #") if " #" in src and '"' not in src.split(" #")[0][-1:] else (src, "", "")
    if src.lstrip().startswith("#"):
        return _span("c", src)
    out, first = [], True
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
        elif t in GUARD or t == ">" or (t.startswith("[") and out and out[-1].endswith(">gone</span>")):
            cls = "guard"                          # gone[remove too] の中身も守り
        elif t in TYPES or t.startswith("["):
            cls = "type"
        elif t in ("->", "|"):
            cls = "op"
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


def highlight(src: str) -> str:
    rows, in_fields = [], False
    for l in src.rstrip("\n").split("\n"):
        if l and l[0] != " " and not l.startswith("#"):
            in_fields = l.split()[0] in ("thing", "input")
        rows.append(line(l, in_fields))
    return "\n".join(rows)
