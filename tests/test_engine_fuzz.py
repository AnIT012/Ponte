"""エンジンをでたらめに叩いても、約束が破れないか（決まった種で何百通りも流す）。

(B) の強さの一部はエンジンなので、エンジンが言語の約束を守ることをここで確かめる。
  1. 状態の値は、宣言した状態のどれか
  2. 状態が変わるのは flow の矢印か、`>` で勝った時だけ
  3. 他人の箱は動かせない・消せない（who）
  4. 通知は持ち主にだけ届く
  5. ログから読み直すと、同じ中身に戻る
"""
import random
from datetime import datetime, timedelta

import pytest

from lang.parser import flow_parts, parse_file
from lang.runtime import Engine, RuleError

SPEC = parse_file("spec/hub_app.lang")
STATES = ["draft", "submitted", "passed", "failed"]
EDGES, WINS = flow_parts(SPEC.find("flow", "Application.status"))
BUTTONS = ["submitted-button", "passed-button", "failed-button", "delete-button", "card", "edit-button"]


def snapshot(eng):
    return {t: {i: dict(b.values) for i, b in bs.items()} for t, bs in eng.boxes.items()}


@pytest.mark.parametrize("seed", range(40))
def test_random_ops_keep_promises(seed, tmp_path):
    rnd = random.Random(seed)
    now = [datetime(2026, 9, 20, 9, 0)]
    store = str(tmp_path / "data.jsonl")
    eng = Engine(SPEC, store=store, clock=lambda: now[0], parallel=False)
    users = {n: eng.login(n) for n in ("alice", "bob")}
    for _ in range(60):
        name = rnd.choice(list(users))
        u = users[name]
        apps = list(eng.boxes["Application"].values())
        op = rnd.choice(["create", "create", "move", "tap", "undo", "remove", "tick", "drag", "update"])
        box = rnd.choice(apps) if apps else None
        owner_before = eng.owner_of(box).name if box else None
        before = dict(box.values) if box else None
        try:
            if op == "create":
                eng.create("Application", {"company": f"C{rnd.randint(1, 9)}",
                                           "deadline": f"9/{rnd.randint(18, 30)} 23:59"}, u)
            elif box is None:
                continue
            elif op == "move":
                eng.move(box, rnd.choice(STATES), u)
            elif op == "drag":
                eng.drag(u, box.id, rnd.choice(STATES))
            elif op == "tap":
                eng.tap(u, rnd.choice(BUTTONS), "Application", box.id)
            elif op == "undo":
                eng.undo(box, u)
            elif op == "remove":
                eng.remove(box, u)
            elif op == "update":
                eng.update(box, {"memo": f"m{rnd.randint(0, 99)}"}, u)
            elif op == "tick":
                now[0] = now[0].replace(hour=21, minute=0) + timedelta(days=rnd.randint(0, 2))
                eng.tick()
                now[0] += timedelta(minutes=1)
        except RuleError:
            pass
        # 3. 他人の箱は、何をしても中身が変わらない・消えない
        if box is not None and owner_before != name and op in ("move", "drag", "tap", "undo", "remove", "update"):
            assert box.id in eng.boxes["Application"], f"{name} が {owner_before} の箱を消した（{op}）"
            assert box.values == before, f"{name} が {owner_before} の箱を変えた（{op}）"
    # 1. 状態は宣言したものだけ
    for b in eng.boxes["Application"].values():
        assert b.values["status"] in STATES
    # 2. 変化は矢印か勝ちだけ（取り消しは直前の1回を戻すだけなので、逆向きも許す）
    for t in eng.trace:
        if t[0] == "move":
            _, _, _, a, b = t
            assert (a, b) in EDGES or (b, a) in WINS, f"{a} -> {b} は flow にありません"
    # 4. 通知は、その箱の持ち主にだけ
    for n in eng.notifications:
        if n["rule"] == "Remind":
            owners = {eng.owner_of(b).name for b in eng.boxes["Application"].values() if eng.label(b) == n["text"]}
            assert not owners or n["user"] in owners
    # 5. 読み直しても同じ
    again = Engine(SPEC, store=store, clock=lambda: now[0], parallel=False)
    assert snapshot(again) == snapshot(eng)
