"""比較実験 v2 の採点。AIには見せない。

(A) AIが Python で全部書いた System と、(B) この言語の spec + AIが書いた action の中身 を、
同じ System の窓口に揃えて、同じ14個のテストを当てる。1テスト＝1つの要件。落ちた数＝バグの数。
"""
from __future__ import annotations

import importlib.util
import sys
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lang.body import Tagged                      # noqa: E402
from lang.fill import action_source, combine      # noqa: E402
from lang.parser import parse, parse_file         # noqa: E402
from lang.runtime import Ctx, Engine, RuleError   # noqa: E402
from lang.body import body_of                     # noqa: E402

SPEC = ROOT / "spec/hub_app.lang"


# ---------------------------------------------------------------------------
# (B) spec + AIの中身を、同じ窓口に揃える
# ---------------------------------------------------------------------------

class LangSystem:
    def __init__(self, now: datetime, body_code: str):
        self.now = now
        spec = parse_file(str(SPEC))
        self.eng = Engine(spec, clock=lambda: self.now)
        a = spec.find("action", "ExtractDeadline")
        mini = parse(combine(action_source(spec, a), body_code))
        ma = mini.find("action", "ExtractDeadline")
        self.eng.bodies = {"ExtractDeadline": body_of(ma, ma.child("do"), {s.name: s for s in mini.decls("shape")})}
        self.seen = 0

    def set_now(self, now):
        self.now = now

    def _u(self, user):
        return self.eng.login(user)

    def _d(self, b):
        return {"id": b.id, "company": b.values["company"], "deadline": b.values["deadline"], "status": b.values["status"]}

    def add(self, user, company, deadline):
        return self.eng.create("Application", {"company": company, "deadline": deadline}, self._u(user)).id

    def apps(self, user):
        u = self._u(user)
        return [self._d(b) for b in self.eng.all("Application") if self.eng.can(u, "see", "Application", b)]

    def due_soon(self, user):
        return [self._d(b) for b in self.eng.list_items("DueSoon", Ctx(self._u(user)))]

    def tick(self):
        before = len(self.eng.notifications)
        self.eng.tick(self.now)
        out = []
        for n in self.eng.notifications[before:]:
            if n["rule"] != "Remind":
                continue
            comp = next((b.values["company"] for b in self.eng.all("Application")
                         if n["text"].startswith(b.values["company"])), n["text"])
            out.append((n["user"], comp))
        return out

    def move(self, user, app_id, to):
        box = self.eng.boxes["Application"].get(app_id)
        if box is None:
            raise ValueError(app_id)
        try:
            self.eng.move(box, to, self._u(user))
        except RuleError as e:
            raise ValueError(str(e))

    def color(self, status):
        return self.eng.match("Application.status to color", status)

    def extract_deadline(self, mail):
        r = self.eng.bodies["ExtractDeadline"].run({"mail": mail})
        return str(r.value) if isinstance(r, Tagged) and r.state == "found" else None


def load_a(path: Path):
    spec = importlib.util.spec_from_file_location(f"a_{abs(hash(str(path)))}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return lambda now: mod.System(now)


def load_b(body_code: str):
    return lambda now: LangSystem(now, body_code)


# ---------------------------------------------------------------------------
# テスト（1つ＝1つの要件）
# ---------------------------------------------------------------------------

T = datetime(2026, 9, 21, 21, 0)
TESTS = []


def test(name, example=False):
    def deco(fn):
        TESTS.append((name, fn, example))
        return fn
    return deco


@test("仕様の例: 9/21 21:00 に 9/24 23:59 の下書きが通知される", example=True)
def t_example(mk):
    s = mk(T)
    s.add("me", "Osaka Gas", "9/24 23:59")
    assert s.tick() == [("me", "Osaka Gas")], s.tick


@test("締切が近い: 下書きだけ・3日を超えるものと過ぎたものは入らない")
def t_due_filter(mk):
    s = mk(T)
    a = s.add("me", "done", "9/22 09:00"); s.move("me", a, "submitted")
    s.add("me", "late", "9/30 10:00")
    s.add("me", "past", "9/20 10:00")
    s.add("me", "soon", "9/23 10:00")
    assert [x["company"] for x in s.due_soon("me")] == ["soon"]


@test("締切が近い: 締切の早い順")
def t_due_sort(mk):
    s = mk(T)
    s.add("me", "b", "9/24 10:00"); s.add("me", "a", "9/22 10:00")
    assert [x["company"] for x in s.due_soon("me")] == ["a", "b"]


@test("通知は21時だけ・持ち主にだけ届く")
def t_owner(mk):
    s = mk(T)
    s.add("me", "Mine", "9/23 10:00"); s.add("you", "Yours", "9/23 10:00")
    got = sorted(s.tick())
    assert got == [("me", "Mine"), ("you", "Yours")], got
    s.set_now(datetime(2026, 9, 21, 20, 0))
    assert s.tick() == []


@test("flow: draft から passed へは飛べない")
def t_flow(mk):
    s = mk(T)
    a = s.add("me", "x", "9/24 10:00")
    try:
        s.move("me", a, "passed")
    except ValueError:
        pass
    else:
        raise AssertionError("draft から passed に動けてしまった")
    s.move("me", a, "submitted"); s.move("me", a, "passed")
    assert s.apps("me")[0]["status"] == "passed"


@test("ぶつかったら failed が勝つ（passed の後の failed は上書き）")
def t_conflict1(mk):
    s = mk(T)
    a = s.add("me", "x", "9/24 10:00"); s.move("me", a, "submitted"); s.move("me", a, "passed"); s.move("me", a, "failed")
    assert s.apps("me")[0]["status"] == "failed"


@test("ぶつかったら failed が勝つ（failed の後の passed はエラーにせず何もしない）")
def t_conflict2(mk):
    s = mk(T)
    a = s.add("me", "x", "9/24 10:00"); s.move("me", a, "submitted"); s.move("me", a, "failed")
    s.move("me", a, "passed")
    assert s.apps("me")[0]["status"] == "failed"


@test("自分の応募しか見えない・動かせない")
def t_who(mk):
    s = mk(T)
    a = s.add("me", "Mine", "9/24 10:00")
    assert s.apps("you") == [] and s.due_soon("you") == []
    try:
        s.move("you", a, "submitted")
    except ValueError:
        pass
    else:
        raise AssertionError("他人の応募を動かせてしまった")


@test("色の表（それ以外は gray）")
def t_color(mk):
    s = mk(T)
    assert [s.color(x) for x in ["draft", "submitted", "passed", "failed", "???"]] == ["orange", "blue", "green", "gray", "gray"]


@test("締切の取り出し: 仕様の例2つ", example=True)
def t_ex_found(mk):
    s = mk(T)
    assert s.extract_deadline("10/15(木)12:00まで") == "10/15 12:00"
    assert s.extract_deadline("【締切9/24 23:59】") == "9/24 23:59"


@test("締切の取り出し: 見つからなければ聞き返す", example=True)
def t_ex_missing(mk):
    assert mk(T).extract_deadline("来週中にご提出ください") is None


@test("締切の取り出し: 2つあったら決めずに聞き返す", example=True)
def t_ex_two(mk):
    assert mk(T).extract_deadline("9/24 23:59 または 9/30 23:59") is None


@test("締切の取り出し: 全角の数字（例に無い）")
def t_ex_fullwidth(mk):
    assert mk(T).extract_deadline("ES締切：１０／１５（木）１２：００") == "10/15 12:00"


@test("同じ応募への同時の書き換えで壊れない")
def t_race(mk):
    s = mk(T)
    a = s.add("me", "x", "9/24 10:00")
    errs = []

    def go():
        try:
            s.move("me", a, "submitted")
        except ValueError:
            pass
        except Exception as e:     # noqa: BLE001
            errs.append(e)
    ts = [threading.Thread(target=go) for _ in range(40)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not errs and s.apps("me")[0]["status"] == "submitted"


TIME_LIMIT = 10     # 1テストの時間。これを超えたら「止まった」（デッドロックなど）として落とす


def run(mk) -> list[tuple[str, bool, bool, str]]:
    out = []
    for name, fn, ex in TESTS:
        box: list = []

        def go():
            try:
                fn(mk)
                box.append(None)
            except Exception as e:  # noqa: BLE001
                box.append(e)
        t = threading.Thread(target=go, daemon=True)
        t.start()
        t.join(TIME_LIMIT)
        if not box:
            out.append((name, False, ex, f"{TIME_LIMIT}秒たっても終わりません（止まっている。デッドロックなど）"))
        elif box[0] is None:
            out.append((name, True, ex, ""))
        else:
            e = box[0]
            out.append((name, False, ex, f"{type(e).__name__}: {e}"[:200]))
    return out
