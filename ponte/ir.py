"""Ponte IR: a checked spec as plain JSON, for the layers underneath (Python today; JS/TS, Go, Java next).

    python -m ponte ir spec.ponte              # the IR
    python -m ponte ir spec.ponte --cases      # the shared test cases (examples) only

The IR is produced only from a spec that passes `ponte check`, so every layer underneath starts from
the same decided spec. It has three parts:

- `source`: the whole spec text (after `use` is resolved). `from_ir` parses it back, so nothing is lost.
- `tree`:   every line as {keyword, text, line, children}, for tools that want the raw structure.
- the readable parts: things, flows, who, lists, rules, relate, actions, matches. Expressions stay as
  the text written in the spec; their meaning is defined by the spec document (docs/言語仕様_v0.3.md).

`cases` are the examples as language-neutral steps (see examples.example_steps). `ponte test` itself
runs these steps, so an implementation in another language that passes every case behaves like Ponte.
"""
from __future__ import annotations

import hashlib
import os

from .checker import check
from .examples import example_steps
from .fill import body_path, normalize_reply
from .parser import Node, Spec, flow_parts, match_arms, parse, relate_lines, thing_fields

VERSION = 1


class NotChecked(Exception):
    """The spec does not pass `ponte check`; no IR is made from an undecided spec."""


def _tree(n: Node) -> dict:
    d = {"keyword": n.keyword, "text": n.text, "line": n.line}
    if n.blocking is not None:
        d["blocking"] = n.blocking
    if n.children:
        d["children"] = [_tree(c) for c in n.children]
    return d


def _texts(n: Node, key: str) -> list[str]:
    return [c.text.strip() for c in n.children_of(key)]


def _one(n: Node, key: str) -> str | None:
    c = n.child(key)
    return c.text.strip() if c is not None else None


def cases(spec: Spec) -> list[dict]:
    """Every example as a test case that any implementation can run."""
    out = []
    for r in spec.decls("rule"):
        for ex in r.children_of("example"):
            out.append({"kind": "rule", "rule": r.name, "line": ex.line, "steps": example_steps(ex)})
    for a in spec.decls("action"):
        param = (a.child("in").text.split() or [""])[0] if a.child("in") else ""
        for ex in a.children_of("example"):
            left, _, right = ex.text.partition("->")
            out.append({"kind": "action", "action": a.name, "line": ex.line,
                        "input": {param: _unquote(left.strip())}, "expect": right.strip()})
        for nv in a.children_of("never"):
            out.append({"kind": "never", "action": a.name, "line": nv.line, "never": nv.text.strip()})
    for m in spec.decls("model"):                       # 使えるモデルの条件（仕様 5章 model）
        out.append({"kind": "model", "model": m.name, "line": m.line})
    return out


def _unquote(s: str) -> str:
    return s[1:-1] if len(s) >= 2 and s[0] == s[-1] == '"' else s


def to_ir(spec: Spec) -> dict:
    errors = [f for f in check(spec) if f.is_error]
    if errors:
        raise NotChecked(f"{len(errors)} error(s): {errors[0]}")
    source = "\n".join(spec.lines)
    things = {}
    for t in spec.decls("thing"):
        things[t.name] = {"line": t.line, "fields": [
            {"name": f.name, "type": f.type, **({"states": f.states} if f.states else {}),
             **({"gone": f.gone} if f.gone else {})} for f in thing_fields(t)]}
    flows = {}
    for f in spec.decls("flow"):
        if f.name == "scene":
            continue
        edges, wins = flow_parts(f)
        flows[f.name] = {"line": f.line, "edges": [list(e) for e in edges], "wins": [list(w) for w in wins]}
    who = []
    for w in spec.decls("who"):
        for c in w.children:
            parts = c.text.split(None, 3)
            if len(parts) >= 3 and parts[0] == "can":
                who.append({"role": c.keyword, "can": parts[1], "thing": parts[2],
                            "where": parts[3][len("where "):] if len(parts) > 3 and parts[3].startswith("where ") else None,
                            "line": c.line})
    lists = {l.name: {"line": l.line, "of": _one(l, "of"), "where": _texts(l, "where"), "sort": _one(l, "sort")}
             for l in spec.decls("list")}
    rules = {}
    for r in spec.decls("rule"):
        rules[r.name] = {"line": r.line, "why": _one(r, "why"), "when": _one(r, "when"), "where": _texts(r, "where"),
                         "do": [_tree(d) for d in r.children_of("do")],
                         "examples": [example_steps(ex) for ex in r.children_of("example")]}
    actions = {}
    for a in spec.decls("action"):
        actions[a.name] = {"line": a.line, "in": _one(a, "in"), "out": _one(a, "out"),
                           "examples": [ex.text.strip() for ex in a.children_of("example")],
                           "never": _texts(a, "never"), "else": _one(a, "else"), "by": _one(a, "by"),
                           "do": _tree(a.child("do")) if a.child("do") is not None else None}
    bodies = {}
    for a in spec.decls("action"):
        path = body_path(spec, a)
        if path and os.path.exists(path):
            bodies[a.name] = open(path, encoding="utf-8").read()
    from .model import decls as model_decls, load as load_model
    models, trained = {}, {}
    for d in model_decls(spec).values():
        models[d.name] = {"line": d.line, "learn": d.target, "from": d.thing, "using": d.using, "require": d.require,
                          "else": d.else_, "layers": d.layers, "epochs": d.epochs,
                          "examples": [{"values": v, "expect": w} for v, w, _ in d.examples]}
        t = load_model(spec, d.name)
        if t is not None:
            trained[d.name] = t
    from .job import read as read_job
    jobs = {}
    for n in spec.decls("job"):
        jb = read_job(n)
        jobs[jb.name] = {"line": jb.line, "run": jb.run, "at": jb.at, "with": jb.raw, "confirm": jb.confirm,
                         "require": [{"fact": f, "op": o, "value": v} for f, o, v, _ in jb.require],
                         "suspect": [{"fact": f, "op": o, "value": v} for f, o, v, _ in jb.suspect]}
    matches = {m.text.strip(): {"line": m.line, "arms": [{"when": lefts, "then": right} for lefts, right, _ in match_arms(m)]}
               for m in spec.decls("match")}
    return {
        "ponte_ir": VERSION,
        "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "source": source,
        "things": things, "flows": flows, "who": who, "lists": lists, "rules": rules,
        "relate": [{"a": a, "kind": k, "b": b, "line": ln} for a, k, b, ln in relate_lines(spec)],
        "actions": actions, "bodies": bodies, "models": models, "trained": trained, "jobs": jobs, "matches": matches,
        "cases": cases(spec),
        "tree": [_tree(n) for n in spec.roots],
    }


def from_ir(ir: dict) -> Spec:
    """IR → spec. Bodies that lived in other files (by code / by ai) are put back as an inline do."""
    if ir.get("ponte_ir") != VERSION:
        raise ValueError(f"unknown IR version: {ir.get('ponte_ir')}")
    lines = ir["source"].split("\n")
    spec = parse(ir["source"])
    extra: list[str] = []
    for a in sorted(spec.decls("action"), key=lambda n: -n.line):   # 下から直すので、上の行番号はずれない
        code = ir.get("bodies", {}).get(a.name)
        if code is None:
            continue
        do_lines, rest, in_do = [], [], False
        for l in normalize_reply(code).splitlines():
            if l.strip() == "do" and not l.startswith(" "):
                in_do = True
                continue
            if in_do and (not l.strip() or l.startswith(" ")):
                do_lines.append(l)
                continue
            in_do = False
            if not l.lstrip().startswith("#"):
                rest.append(l)
        start, end = a.line - 1, a.line
        while end < len(lines) and (not lines[end].strip() or lines[end].startswith(" ")):
            end += 1
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        block = [l for l in lines[start:end] if not l.strip().startswith("by ")]
        block += ["  do"] + [("  " + l) if l.strip() else "" for l in do_lines]
        lines[start:end] = [l.rstrip() for l in block]
        extra += [""] + rest
    back = parse("\n".join(lines + extra) + "\n")
    back.trained_models = dict(ir.get("trained", {}))    # model の学んだ結果も IR から持って来る
    return back


def run_case(spec: Spec, case: dict, trained: dict | None = None):
    """Run one shared test case on the Python engine (the reference implementation). → examples.Result"""
    from .body import input_names, out_states_of, parse_expected, same
    from .examples import Result, run_steps
    from .fill import check_nevers, load_body
    if case["kind"] == "rule":
        return run_steps(spec, spec.find("rule", case["rule"]), case["steps"], case["line"])
    if case["kind"] == "model":
        from .model import decls as model_decls, verdict
        d = model_decls(spec)[case["model"]]
        t = (trained or {}).get(d.name)
        if t is None:                        # 学んでいないモデルは ponte test と同じく飛ばす
            return Result(d.name, case["line"], True, "skipped")
        ok, why = verdict(spec, d, t)
        return Result(d.name, case["line"], ok, "; ".join(why))
    a = spec.find("action", case["action"])
    body = load_body(spec, a)
    if body is None:                     # 中身がまだ無い action は ponte test と同じく飛ばす（失敗にはしない）
        return Result(a.name, case["line"], True, "skipped")
    if case["kind"] == "action":
        try:
            got = body.run(case["input"])
        except Exception as e:
            return Result(a.name, case["line"], False, f"{type(e).__name__}: {e}")
        ok = same(got, parse_expected(case["expect"], out_states_of(a)))
        return Result(a.name, case["line"], ok, "" if ok else f"{case['input']} -> {case['expect']}, got {got}")
    probs = [p for p in check_nevers(a, body, input_names(a)[0]) if p.startswith(f"never {case['never']}")]
    return Result(a.name, case["line"], not probs, "; ".join(probs))
