"""`with` and `confirm`: compare what was declared with what the lower layer reports it used (spec 5章 with と confirm)."""
from __future__ import annotations

import re

_DUR = re.compile(r"^(-?\d+(?:\.\d+)?)\s*(ms|milliseconds?|s|seconds?|minutes?|hours?)$")
_SECONDS = {"ms": 0.001, "millisecond": 0.001, "milliseconds": 0.001, "s": 1, "second": 1, "seconds": 1,
            "minute": 60, "minutes": 60, "hour": 3600, "hours": 3600}


def value(text) -> object:
    """One value → a comparable Python value: numbers, periods (in seconds), yes/no, text."""
    if isinstance(text, bool) or isinstance(text, (int, float)):
        return text
    t = str(text).strip()
    if t in ("yes", "true", "True"):
        return True
    if t in ("no", "false", "False"):
        return False
    m = _DUR.match(t)
    if m:
        return float(m.group(1)) * _SECONDS[m.group(2)]
    try:
        return float(t) if re.search(r"[.eE]", t) else int(t)
    except ValueError:
        return t[1:-1] if len(t) >= 2 and t[0] == t[-1] == '"' else t


def parse_with(text: str) -> tuple[dict, dict, list[str]]:
    """`lr 1.25e-4, timeout 5 seconds` → ({"lr": 0.000125, "timeout": 5.0}, {"lr": "1.25e-4", ...}, 読めない所)"""
    out, raw, bad = {}, {}, []
    for part in [p.strip() for p in text.split(",") if p.strip()]:
        w = part.split(None, 1)
        if len(w) != 2 or not re.fullmatch(r"[a-z_]\w*", w[0]):
            bad.append(part)
            continue
        out[w[0]] = value(w[1])
        raw[w[0]] = w[1].strip()
    return out, raw, bad


def names(text: str) -> list[str]:
    """confirm の名前（`名前 値` と書いたものも、名前だけを返す）"""
    return [x.split()[0] for x in [p.strip() for p in text.split(",")] if x]


def expected(text: str) -> tuple[dict, dict]:
    """confirm の `名前 値`（渡さないが、こうなっているはずの値）→ (値, 書いたままの値)"""
    out, raw = {}, {}
    for part in [p.strip() for p in text.split(",") if p.strip()]:
        w = part.split(None, 1)
        if len(w) == 2:
            out[w[0]] = value(w[1])
            raw[w[0]] = w[1].strip()
    return out, raw


def _same(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or (isinstance(a, bool) and isinstance(b, bool) and a == b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 1e-9 * max(abs(a), abs(b), 1e-300)
    return str(a) == str(b)


def problems(declared: dict, wanted: list[str], reported: dict, raw: dict | None = None) -> list[str]:
    """Every name in confirm whose reported value is missing or differs from the declaration."""
    out = []
    for n in wanted:
        shown = (raw or {}).get(n, declared.get(n))
        if n not in reported:
            out.append(f"confirm {n}: 下の層が使った値を報告していません（宣言は {shown}）")
        elif not _same(declared.get(n), value(reported[n])):
            out.append(f"confirm {n}: 宣言は {shown} なのに、実際に使われたのは {reported[n]} です")
    return out


def parts(node) -> tuple[dict, dict, list[str]]:
    """部品の with と confirm → (宣言した値, 書いたままの値, 照合する名前)"""
    settings, raw, wanted = {}, {}, []
    for w in node.children_of("with"):                 # 何行に分けて書いてもよい
        s, r, _ = parse_with(w.text)
        settings.update(s)
        raw.update(r)
    for c in node.children_of("confirm"):
        wanted += names(c.text)
    return settings, raw, wanted


def declared(node) -> tuple[dict, dict]:
    """照合に使う値: with の値と、confirm に書いた `名前 値`（こちらは下の層に渡さない）"""
    settings, raw, _ = parts(node)
    vals, shown = dict(settings), dict(raw)
    for c in node.children_of("confirm"):
        e, r = expected(c.text)
        vals.update(e)
        shown.update(r)
    return vals, shown
