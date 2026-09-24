"""`model`: a classifier learned from the records of a thing, kept inside a contract.

    model Churn
      learn    will_leave from Customer
      using    visits, spend, months
      require  accuracy at least 80%
      else     skip
      how      layers 16 8, epochs 200
      example  visits 0, spend 0, months 1 -> yes

- learn:   the state field to predict, and the thing whose records teach it.
- using:   the fields the model may look at (numbers or states). Nothing else is ever seen.
- require: the accuracy it must reach on records held back from training. Below it, ponte test fails.
- else:    what happens when there is no usable model (not trained, trained for an older definition,
           below `require`, or getting an example wrong). Required.
- how:     optional. Hidden layer sizes and the number of passes over the data.
- example: cases it must always get right. They are checked like any other example.

`ponte train spec.ponte` learns from the app's stored records (or `--csv`) and writes
`<spec>.models/<Name>.json`. The network itself is ponte/nn.py (plain Python).
The meaning of every part is fixed in docs/言語仕様_v0.3.md (model); this file follows it.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from .nn import MLP
from .parser import Node, Spec, thing_fields

NUMERIC = ("number", "count", "money", "percent")


@dataclass
class ModelDecl:
    name: str
    line: int
    target: str = ""
    thing: str = ""
    using: list[str] = field(default_factory=list)
    require: float | None = None
    else_: str | None = None
    layers: list[int] = field(default_factory=lambda: [16, 8])
    epochs: int = 200
    examples: list[tuple[dict, str, int]] = field(default_factory=list)
    problems: list[tuple[int, str]] = field(default_factory=list)     # (行, 何が読めないか)


def _pct(text: str) -> float | None:
    m = re.fullmatch(r"(?:accuracy\s+)?at least\s+(\d+(?:\.\d+)?)%", text.strip())
    return float(m.group(1)) / 100 if m else None


def read(node: Node) -> ModelDecl:
    d = ModelDecl(node.name, node.line)
    for c in node.children:
        k, t = c.keyword, c.text.strip()
        if k == "learn":
            m = re.fullmatch(r"(\w+)\s+from\s+([A-Z]\w*)", t)
            if m:
                d.target, d.thing = m.group(1), m.group(2)
            else:
                d.problems.append((c.line, "learn は `learn 項目 from Thing` と書きます"))
        elif k == "using":
            d.using = [x.strip() for x in t.split(",") if x.strip()]
        elif k == "require":
            d.require = _pct(t)
            if d.require is None or not t.startswith("accuracy"):
                d.problems.append((c.line, "require は `require accuracy at least 80%` と書きます"))
        elif k == "else":
            d.else_ = t
        elif k == "how":
            for part in [p.strip() for p in t.split(",")]:
                m1 = re.fullmatch(r"layers((?:\s+\d+)+)", part)
                m2 = re.fullmatch(r"epochs\s+(\d+)", part)
                if m1:
                    d.layers = [int(x) for x in m1.group(1).split()]
                elif m2:
                    d.epochs = int(m2.group(1))
                else:
                    d.problems.append((c.line, f"how に書けるのは `layers 16 8` と `epochs 200` です: '{part}'"))
        elif k == "example":
            left, arrow, right = t.partition("->")
            vals = {}
            for pair in [p.strip() for p in left.split(",") if p.strip()]:
                w = pair.split(None, 1)
                if len(w) == 2:
                    vals[w[0]] = w[1].strip().strip('"')
            if not arrow or not vals or not right.strip():
                d.problems.append((c.line, "example は `example 項目 値, 項目 値 -> 答え` と書きます"))
            else:
                d.examples.append((vals, right.strip(), c.line))
        else:
            d.problems.append((c.line, f"model に「{k}」という部品はありません（learn / using / require / else / how / example）"))
    return d


def decls(spec: Spec) -> dict[str, ModelDecl]:
    return {n.name: read(n) for n in spec.decls("model")}


def fields_of(spec: Spec, thing: str) -> dict:
    t = spec.find("thing", thing)
    return {f.name: f for f in thing_fields(t)} if t is not None else {}


def classes(spec: Spec, d: ModelDecl) -> list[str]:
    f = fields_of(spec, d.thing).get(d.target)
    return list(f.states) if f is not None and f.states else []


# ---------------------------------------------------------------------------
# data → numbers
# ---------------------------------------------------------------------------

def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", "").replace("¥", "").replace("円", ""))
    except (TypeError, ValueError):
        return None


def encoder(spec: Spec, d: ModelDecl, rows: list[dict]) -> list[dict]:
    """How each `using` field becomes numbers: numbers are scaled with the training data's mean and spread,
    states become one number per state (1 for the one it is, 0 for the rest)."""
    fs = fields_of(spec, d.thing)
    enc = []
    for name in d.using:
        f = fs[name]
        if f.states:
            enc.append({"field": name, "states": list(f.states)})
        else:
            xs = [x for x in (_num(r.get(name)) for r in rows) if x is not None] or [0.0]
            mean = sum(xs) / len(xs)
            sd = (sum((x - mean) ** 2 for x in xs) / len(xs)) ** 0.5 or 1.0
            enc.append({"field": name, "mean": mean, "sd": sd})
    return enc


def encode(enc: list[dict], row: dict) -> list[float]:
    out: list[float] = []
    for e in enc:
        v = row.get(e["field"])
        if "states" in e:
            out += [1.0 if str(v) == s else 0.0 for s in e["states"]]
        else:
            x = _num(v)
            out.append(0.0 if x is None else (x - e["mean"]) / e["sd"])
    return out


# ---------------------------------------------------------------------------
# train / save / predict
# ---------------------------------------------------------------------------

def path_of(spec: Spec, name: str) -> str:
    return f"{spec.path}.models{os.sep}{name}.json"


def split(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Every fifth record is held back to measure accuracy. The same records always land on the same side."""
    train = [r for i, r in enumerate(rows) if i % 5 != 4]
    held = [r for i, r in enumerate(rows) if i % 5 == 4]
    return train, held


def train(spec: Spec, d: ModelDecl, rows: list[dict], seed: int = 0) -> dict:
    cls = classes(spec, d)
    rows = [r for r in rows if str(r.get(d.target)) in cls]
    if len(rows) < 20:
        raise ValueError(f"model {d.name}: 学ぶレコードが足りません（{len(rows)}件。20件以上必要です）")
    tr, held = split(rows)
    enc = encoder(spec, d, tr)
    X = [encode(enc, r) for r in tr]
    y = [cls.index(str(r[d.target])) for r in tr]
    net = MLP([len(X[0])] + d.layers + [len(cls)], seed=seed)
    losses = net.fit(X, y, epochs=d.epochs, lr=0.01, seed=seed)
    hits = sum(cls[_argmax(net.predict_proba(encode(enc, r)))] == str(r[d.target]) for r in held)
    return {"model": d.name, "fingerprint": fingerprint(spec, d), "learn": d.target, "from": d.thing, "using": d.using, "classes": cls,
            "encoder": enc, "net": net.to_dict(), "records": len(rows), "held_back": len(held),
            "accuracy": hits / len(held) if held else 0.0, "loss": losses[-1] if losses else None}


def save(spec: Spec, trained: dict) -> str:
    p = path_of(spec, trained["model"])
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(trained, f, ensure_ascii=False)
    return p


def load(spec: Spec, name: str) -> dict | None:
    carried = getattr(spec, "trained_models", None)      # IR から戻した仕様は、学んだ結果を持って来ている
    if carried is not None:
        return carried.get(name)
    p = path_of(spec, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def predict(trained: dict, row: dict) -> str:
    """The class the model gives for a record. Only the `using` fields are passed in."""
    net = MLP.from_dict(trained["net"])
    seen = {k: row.get(k) for k in trained["using"]}
    return trained["classes"][_argmax(net.predict_proba(encode(trained["encoder"], seen)))]


def fingerprint(spec: Spec, d: ModelDecl) -> str:
    """What the model was trained for. A trained file for another definition is not used."""
    import hashlib
    fs = fields_of(spec, d.thing)
    parts = [d.target, d.thing, ",".join(d.using), repr(d.layers), str(d.epochs)]
    parts += [f"{n}:{fs[n].type}:{fs[n].states}" for n in [d.target] + d.using if n in fs]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def verdict(spec: Spec, d: ModelDecl, trained: dict | None) -> tuple[bool, list[str]]:
    """Whether the model may be used, and every reason it may not. The rules are in the spec (model)."""
    if trained is None:
        return False, [f"model {d.name}: まだ学習していません（ponte train）"]
    why = []
    if trained.get("fingerprint") != fingerprint(spec, d):
        why.append(f"model {d.name}: 学習したときと定義が違います。学習し直してください（ponte train）")
        return False, why
    if d.require is not None and trained["accuracy"] < d.require:
        why.append(f"model {d.name}: 正解率 {trained['accuracy']:.0%} が require の {d.require:.0%} に届きません")
    for vals, want, line in d.examples:
        got = predict(trained, vals)
        if got != want:
            why.append(f"model {d.name}: example（L{line}）は {want} のはずが {got}")
    return not why, why


def _argmax(p: list[float]) -> int:
    return max(range(len(p)), key=lambda i: p[i])
