"""rule の example を実行エンジンで流す（仕様 v0.2 9章）。

  given   箱の名前（下に「項目 値」を1行1つ）  … 前の状態（出来事は起こさない）
  at "..." / says "..." / taps X on 箱(...) / gets Conn 出来事 "..." / adds 箱（下に中身）   … 出来事
  expect notify "..." / expect 箱の名前 is 状態（下に中身）/ expect scene X / expect 画面 shows N cards / expect no 箱 / expect 2 箱 / expect 箱（下に中身）/ expect nothing
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from .parser import Node, Spec
from .runtime import Ctx, Engine, NotAllowed
from .values import parse_time, unquote


def record(node: Node, thing: str) -> tuple[str, dict[str, str]]:
    """`given Application` と、その下の `company "Osaka Gas"` の行 → ("Application", {...})"""
    vals = {}
    for c in node.children:
        vals[c.keyword] = unquote(c.text)
    return thing, vals

def example_steps(ex: Node) -> list[dict]:
    """example の手順を、言語に依らない形にする（IR と共通テストでも同じ形を使う）。
    1つの手順 = {"kind": given/adds/at/says/taps/gets/expect, "text": 行の残り, "values": {項目: 値}, "line": 行}"""
    return [{"kind": c.keyword, "text": c.text.strip(), "values": {g.keyword: unquote(g.text) for g in c.children},
             "line": c.line} for c in ex.children]


EXAMPLE_YEAR = 2026   # example の日時は年が無い。年は推測しないので、決まった年で読む（QUESTIONS_v0.2 R5）


@dataclass
class Result:
    rule: str
    line: int
    ok: bool
    message: str = ""
    trace: tuple = ()


def run_example(spec: Spec, rule: Node, ex: Node) -> Result:
    return run_steps(spec, rule, example_steps(ex), ex.line)


def run_steps(spec: Spec, rule: Node, steps: list[dict], line: int) -> Result:
    """手順（example_steps の形）を実行エンジンで流す。ponte test も共通テストの基準もこれを使う。"""
    now = [datetime(EXAMPLE_YEAR, 1, 1, 0, 0)]
    try:
        for c in steps:
            if c["kind"] == "at":
                now[0] = parse_time(unquote(c["text"]), EXAMPLE_YEAR)
        eng = Engine(spec, clock=lambda: now[0], parallel=False)
        me = eng.login("me")
        ctx = Ctx(me)
    except Exception as e:   # 動かす前の準備で止まっても、失敗として返す（check が先に止めるはず）
        return Result(rule.name, line, False, f"{type(e).__name__}: {e}")
    try:
        for c in steps:
            k, t = c["kind"], c["text"]
            if k == "given":
                thing, vals = t.split()[0], dict(c["values"])
                vals = _refs(eng, thing, vals)
                same = [b for b in eng.all("User") if b.values.get("name") == vals.get("name")] if thing == "User" else []
                if same:                          # `given User name "me" role admin` は、例を動かす人そのもの
                    same[0].values.update(vals)
                    me = eng.login("me")
                    ctx = Ctx(me)
                else:
                    eng.create(thing, vals, me, fire=False, check=False)
            elif k == "adds":                       # 人が作った（出来事も起きる）: adds Expense の下に中身
                thing, vals = t.split()[0], dict(c["values"])
                eng.create(thing, _refs(eng, thing, vals), me)
            elif k == "at":
                eng.run_rule(rule, Ctx(None))
            elif k == "says":
                ctx = eng.says(me, unquote(t))
            elif k == "taps":
                m = re.match(r"^(\S+) on (\w+)$", t)
                if not c["values"]:                             # 画面そのものを押した
                    ctx = eng.tap(me, m.group(1), m.group(2))
                    continue
                thing, vals = m.group(2), dict(c["values"])
                boxes = eng.find(thing, _refs(eng, thing, vals))
                if not boxes:
                    return Result(rule.name, c["line"], False, f"taps の対象が見つかりません: {m.group(2)} {vals}")
                when = rule.child("when")               # when の無い rule（relate の then で動くもの）でも押せる
                on = re.search(r"\bon (\w+)$", when.text) if when is not None else None
                try:
                    ctx = eng.tap(me, m.group(1), on.group(1) if on else thing, boxes[0].id)
                except NotAllowed:                      # 見られない箱のボタン → 何も起きない（画面にもボタンが出ない）
                    pass
            elif k == "gets":
                m = re.match(r'^(\w+) (.+?) "(.*)"$', t)
                ctx = eng.gives(m.group(1), m.group(2), m.group(3))
            elif k == "expect":
                bad = _expect(eng, t, ctx, c["values"])
                if bad:
                    why = [n["text"] for n in eng.notifications if n["text"].startswith("うまくいきませんでした")]
                    if why and not t.startswith("notify"):     # 途中で止まった理由も見せる
                        bad += f"（途中で止まっています: {why[0].split(': ', 1)[-1]}）"
                    return Result(rule.name, c["line"], False, bad, tuple(eng.trace))
    except Exception as e:   # 例の途中で止まったら、それも失敗として返す
        return Result(rule.name, line, False, f"{type(e).__name__}: {e}", tuple(eng.trace))
    return Result(rule.name, line, True, "", tuple(eng.trace))


def _refs(eng: Engine, thing: str, vals: dict) -> dict:
    """別の thing を指す項目は、その箱の文字（名前など）で書ける：`item "カメラ"`"""
    out = dict(vals)
    for k, v in vals.items():
        f = eng.fields.get(thing, {}).get(k)
        if f is None or f.type not in eng.fields or v in eng.boxes[f.type]:
            continue
        hits = [b for b in eng.boxes[f.type].values() if v in b.values.values() or eng.label(b) == v]
        if len(hits) != 1:
            raise ValueError(f"{thing}.{k}: 「{v}」の {f.type} が{'見つかりません' if not hits else '2つ以上あります'}（先に given で書く）")
        out[k] = hits[0].id
    return out


def _expect(eng: Engine, t: str, ctx: Ctx, values: dict | None = None) -> str | None:
    m = re.match(r'^notify "(.*)"$', t)
    if m:
        if any(m.group(1) in n["text"] for n in eng.notifications):
            return None
        return f"notify 「{m.group(1)}」のはずが {[n['text'] for n in eng.notifications]}"
    m = re.match(r"^([A-Z]\w*) is (\w+)$", t)
    if m and m.group(1) in eng.fields:
        thing, vals = m.group(1), dict(values or {})
        boxes = eng.find(thing, _refs(eng, thing, vals))
        if not boxes:
            return f"{thing} {vals} が見つかりません"
        states = [v for b in boxes for k, v in b.values.items() if eng.fields[thing][k].states]
        return None if m.group(2) in states else f"{thing} {vals} は {m.group(2)} のはずが {states}"
    m = re.match(r"^scene (\w+)$", t)
    if m:
        return None if ctx.nav == m.group(1) else f"scene {m.group(1)} のはずが {ctx.nav}"
    m = re.match(r"^(\w+) shows (\d+) (cards?|rows?|items?)$", t)
    if m:
        from .server import App
        if not eng.spec.find("scene", m.group(1)):
            return f"scene {m.group(1)} がありません（shows は scene の名前に使います）"
        app = App(eng.spec, eng)
        me = eng.login("me")
        v = app.view(m.group(1), me, {}, None, None, "ja")
        rows = sum(len(b.get("rows", [])) for s in v["slots"] for b in s["blocks"])
        return None if rows == int(m.group(2)) else f"{m.group(1)} に {m.group(2)} 件のはずが {rows} 件"
    if re.fullmatch(r"[A-Z]\w*", t) and t in eng.fields:      # expect Expense の下に中身 → その中身の箱がある
        thing, vals = t, dict(values or {})
        if eng.find(thing, _refs(eng, thing, vals)):
            return None
        return f"{thing} {vals} が見つかりません（あるのは {[b.values for b in eng.all(thing)][:3]}）"
    m = re.match(r"^(no|\d+) ([A-Z]\w*)$", t)
    if m and m.group(2) in eng.fields:                # expect no Loan / expect 2 Loan
        want = 0 if m.group(1) == "no" else int(m.group(1))
        got = len(eng.all(m.group(2)))
        return None if got == want else f"{m.group(2)} は {want} 件のはずが {got} 件"
    if t == "nothing":
        return None if not eng.notifications else f"何も起きないはずが {eng.notifications}"
    return f"expect の書き方が分かりません: '{t}'"


def run_action_examples(spec: Spec) -> list[Result]:
    """中身（by ai / by code）がある action の example を流す。中身が無いものは流さない。"""
    from .body import parse_expected, same, out_states_of, input_names
    from .fill import load_body
    out = []
    for a in spec.decls("action"):
        try:
            body = load_body(spec, a)
        except Exception as e:
            out.append(Result(a.name, a.line, False, f"中身が読めません: {e}"))
            continue
        if body is None:
            continue
        outs = out_states_of(a)
        for ex in a.children_of("example"):
            left, right = [x.strip() for x in ex.text.split("->", 1)]
            try:
                got = body.run({input_names(a)[0]: unquote(left)})
            except Exception as e:
                out.append(Result(a.name, ex.line, False, f"{left} で止まりました: {e}"))
                continue
            ok = same(got, parse_expected(right, outs))
            out.append(Result(a.name, ex.line, ok, "" if ok else f"{left} → {right} のはずが {got}"))
        from .fill import check_nevers            # 機械で確かめられる never も流す
        for n in a.children_of("never"):
            probs = [p for p in check_nevers(a, body, input_names(a)[0]) if p.startswith(f"never {n.text.strip()}")]
            out.append(Result(a.name, n.line, not probs, "; ".join(probs)))
    return out


def run_examples(spec: Spec) -> list[Result]:
    out = run_action_examples(spec)
    for r in spec.decls("rule"):
        for ex in r.children_of("example"):
            out.append(run_example(spec, r, ex))
    return out


@dataclass
class Hole:
    line: int
    message: str


def holes(spec: Spec, results: list[Result]) -> list[Hole]:
    """example で一度も確かめていない所（穴）。通っていても、ここは誰も見ていない。

      - 出来事（when）がある rule なのに、example が無く、どの example の中でも動いていない
      - flow の矢印を、どの example も通っていない
      - action の out の答えの形を、どの example も出していない
    """
    from .body import out_states_of
    from .parser import flow_parts
    trace = [t for r in results for t in r.trace]
    ran = {t[1] for t in trace if t[0] == "rule"}
    moved = {(t[1], t[2], t[3], t[4]) for t in trace if t[0] == "move"}
    tested_actions = {a.name for a in spec.decls("action") if a.children_of("example")}
    out: list[Hole] = []
    for r in spec.decls("rule"):
        if not r.child("when") or r.children_of("example") or r.name in ran:   # 他の example の中で動いていれば見ている
            continue
        dos = [d.text.strip() for d in r.children_of("do")]
        if len(dos) == 1 and dos[0] in tested_actions:      # 中身は action の example で確かめている
            continue
        out.append(Hole(r.line, f"rule {r.name}: when があるのに example がありません"))
    for f in spec.decls("flow"):
        if "." not in f.name:
            continue
        thing, fld = f.name.split(".", 1)
        edges, _ = flow_parts(f)
        for a, b in edges:
            if (thing, fld, a, b) not in moved:
                out.append(Hole(f.line, f"flow {f.name}: {a} -> {b} をどの example も通っていません"))
    for a in spec.decls("action"):
        seen = {ex.text.split("->", 1)[1].split()[0] for ex in a.children_of("example") if "->" in ex.text}
        for s in out_states_of(a):
            if s not in seen:
                out.append(Hole(a.line, f"action {a.name}: 答えが {s} になる example がありません"))
    return out
