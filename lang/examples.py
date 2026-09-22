"""rule の example を実行エンジンで流す（仕様 v0.2 9章）。

  given   箱(項目 値, ...)      … 前の状態（出来事は起こさない）
  at "..." / says "..." / taps X on 箱(...) / gets Conn 出来事 "..."   … 出来事
  expect notify "..." / expect 箱(...) is 状態 / expect scene X / expect nothing
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from .parser import Node, Spec
from .runtime import Ctx, Engine
from .values import parse_record, parse_time, unquote

EXAMPLE_YEAR = 2026   # example の日時は年が無い。年は推測しないので、決まった年で読む（QUESTIONS_v0.2 R5）


@dataclass
class Result:
    rule: str
    line: int
    ok: bool
    message: str = ""


def run_example(spec: Spec, rule: Node, ex: Node) -> Result:
    now = [datetime(EXAMPLE_YEAR, 1, 1, 0, 0)]
    for c in ex.children:
        if c.keyword == "at":
            now[0] = parse_time(unquote(c.text), EXAMPLE_YEAR)
    eng = Engine(spec, clock=lambda: now[0], parallel=False)
    me = eng.login("me")
    ctx = Ctx(me)
    try:
        for c in ex.children:
            k, t = c.keyword, c.text.strip()
            if k == "given":
                thing, vals = parse_record(t)
                eng.create(thing, vals, me, fire=False, check=False)
            elif k == "at":
                eng.run_rule(rule, Ctx(None))
            elif k == "says":
                ctx = eng.says(me, unquote(t))
            elif k == "taps":
                m = re.match(r"^(\S+) on (.+)$", t)
                if re.fullmatch(r"\w+", m.group(2)):          # 画面そのものを押した
                    ctx = eng.tap(me, m.group(1), m.group(2))
                    continue
                thing, vals = parse_record(m.group(2))
                boxes = eng.find(thing, vals)
                if not boxes:
                    return Result(rule.name, c.line, False, f"taps の対象が見つかりません: {m.group(2)}")
                on = re.search(r"\bon (\w+)$", rule.child("when").text)
                ctx = eng.tap(me, m.group(1), on.group(1) if on else thing, boxes[0].id)
            elif k == "gets":
                m = re.match(r'^(\w+) (.+?) "(.*)"$', t)
                ctx = eng.gives(m.group(1), m.group(2), m.group(3))
            elif k == "expect":
                bad = _expect(eng, t, ctx)
                if bad:
                    return Result(rule.name, c.line, False, bad)
    except Exception as e:   # 例の途中で止まったら、それも失敗として返す
        return Result(rule.name, ex.line, False, f"{type(e).__name__}: {e}")
    return Result(rule.name, ex.line, True)


def _expect(eng: Engine, t: str, ctx: Ctx) -> str | None:
    m = re.match(r'^notify "(.*)"$', t)
    if m:
        if any(m.group(1) in n["text"] for n in eng.notifications):
            return None
        return f"notify 「{m.group(1)}」のはずが {[n['text'] for n in eng.notifications]}"
    m = re.match(r"^(\w+\(.*\)) is (\w+)$", t)
    if m:
        thing, vals = parse_record(m.group(1))
        boxes = eng.find(thing, vals)
        if not boxes:
            return f"{m.group(1)} が見つかりません"
        states = [v for b in boxes for k, v in b.values.items() if eng.fields[thing][k].states]
        return None if m.group(2) in states else f"{m.group(1)} は {m.group(2)} のはずが {states}"
    m = re.match(r"^scene (\w+)$", t)
    if m:
        return None if ctx.nav == m.group(1) else f"scene {m.group(1)} のはずが {ctx.nav}"
    if t == "nothing":
        return None if not eng.notifications else f"何も起きないはずが {eng.notifications}"
    return f"expect の書き方が分かりません: '{t}'"


def run_examples(spec: Spec) -> list[Result]:
    out = []
    for r in spec.decls("rule"):
        for ex in r.children_of("example"):
            out.append(run_example(spec, r, ex))
    return out
