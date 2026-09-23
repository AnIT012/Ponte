"""実行エンジン（仕様 v0.2）。spec を直接読んで動かす。依存は Python の標準機能だけ。

- 箱（thing 1件）ごとにロックを持ち、同じ箱への書き換えは1つずつ。箱をまたぐ処理は並列。
- flow の -> の通りにしか動かない。ぶつかったら > の勝ち。
- 出来事（時間・発言・タップ・データの変化・外から届いたもの）で rule が動く。
- relate の then / then no / before / > / else を守る。
- who に書いてないことは誰もできない。
- データは1つのファイルに書き足していく（ログ）。起動時に読み直す。

仕様に無くて仮で決めた動きは QUESTIONS_v0.2.md の R 節。
"""
from __future__ import annotations

import itertools
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

from .parser import Node, Spec, flow_parts, flow_states, match_arms, relate_lines, thing_fields
from .values import format_monthday, parse_record, parse_time, unquote, within


class RuleError(Exception):
    """rule がやり遂げられなかった（relate の else に進む）"""


class NotAllowed(RuleError):
    """who で許されていない"""


class ActionEmpty(RuleError):
    """action の中身がまだ無い"""


@dataclass
class Box:
    thing: str
    id: str
    values: dict
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    prev: dict = field(default_factory=dict)          # flow の項目ごとの直前の状態
    done: set = field(default_factory=set)            # この箱で済んだ rule
    blocked: set = field(default_factory=set)         # then no で止められた rule


@dataclass
class User:
    id: str                 # User 箱の id
    name: str
    roles: set = field(default_factory=lambda: {"user"})


@dataclass
class Ctx:
    user: User | None
    this: Box | None = None
    vars: dict = field(default_factory=dict)
    nav: str | None = None
    payload: str | None = None     # 外から届いたもの（メール本文など）


class Engine:
    def __init__(self, spec: Spec, store: str | None = None, clock=None, parallel: bool = True):
        self.spec = spec
        self.clock = clock or datetime.now
        self.parallel = parallel
        self.store = store
        self._ids = itertools.count(1)
        self._lock = threading.RLock()
        self.boxes: dict[str, dict[str, Box]] = {}
        self.notifications: list[dict] = []
        self.listeners: list = []
        self.connectors: dict = {}        # (connect 名, 動詞) → 関数
        self.action_impls: dict = {}      # action 名 → 関数（by code の代わりに Python から入れる口）
        self._pending: list[tuple[Node, Ctx]] = []   # before 待ちの rule
        self._fired_today: set = set()
        self._read_spec()
        self.bodies = {}
        from .fill import load_body     # action の中身（by ai / by code）
        for name, a in self.actions.items():
            try:
                b = load_body(self.spec, a)
            except Exception:
                b = None
            if b is not None:
                self.bodies[name] = b
        for t in self.fields:
            self.boxes[t] = {}
        if store and os.path.exists(store):
            self._replay()

    # ------------------------------------------------------------------
    # spec を読む
    # ------------------------------------------------------------------
    def _read_spec(self):
        s = self.spec
        self.fields = {t.name: {f.name: f for f in thing_fields(t)} for t in s.decls("thing")}
        self.flows = {}
        for f in s.decls("flow"):
            if "." in f.name:
                t, fld = f.name.split(".", 1)
                edges, wins = flow_parts(f)
                self.flows[(t, fld)] = (edges, wins, flow_states(f))
        self.lists = {l.name: l for l in s.decls("list")}
        self.matches = {m.text: m for m in s.decls("match")}   # 「Application.status to color」と「... to icon」を別々に持つ
        self.rules = {r.name: r for r in s.decls("rule")}
        self.actions = {a.name: a for a in s.decls("action")}
        self.relates = relate_lines(s)
        self.who = []
        for w in s.decls("who"):
            for c in w.children:
                m = re.match(r"^(\w+)\s+can\s+(\w+)\s+(\w+)(?:\s+where\s+(.+))?$", c.raw)
                if m:
                    self.who.append(m.groups())

    # ------------------------------------------------------------------
    # 保存（ログ）
    # ------------------------------------------------------------------
    def _log(self, rec: dict):
        if not self.store:
            return
        with self._lock, open(self.store, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _replay(self):
        with open(self.store, encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec["t"] == "create":
                    self.boxes.setdefault(rec["thing"], {})[rec["id"]] = Box(rec["thing"], rec["id"], rec["values"])
                    n = int(rec["id"].split("-")[-1])
                    self._ids = itertools.count(max(n + 1, next(self._ids)))
                elif rec["t"] == "set":
                    b = self.boxes[rec["thing"]][rec["id"]]
                    b.prev[rec["field"]] = b.values.get(rec["field"])
                    b.values[rec["field"]] = rec["value"]
                elif rec["t"] == "remove":
                    self.boxes[rec["thing"]].pop(rec["id"], None)

    def _changed(self):
        for fn in list(self.listeners):
            try:
                fn()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 人
    # ------------------------------------------------------------------
    def login(self, name: str, roles: set | None = None) -> User:
        """User 箱を名前で探す。無ければ作る。"""
        if "User" in self.fields:
            for b in self.boxes["User"].values():
                if b.values.get("name") == name:
                    return User(b.id, name, roles or {"user"})
            b = self.create("User", {"name": name}, user=None, fire=False, check=False)
            return User(b.id, name, roles or {"user"})
        return User(name, name, roles or {"user"})

    def can(self, user: User | None, verb: str, thing: str, box: Box | None) -> bool:
        if user is None:
            return True   # 時間や外から届いた出来事で動く rule は、仕組みとして動く
        for role, v, t, where in self.who:
            if role != "user" and role not in user.roles:
                continue
            if role == "nobody":
                continue
            if v == "do" and t == "everything":
                return True
            if t != thing or (v != verb and not (v == "change" and verb in ("create", "move"))):
                continue
            if where is None or box is None or self._where(box, where, Ctx(user)):
                return True
        return False

    # ------------------------------------------------------------------
    # 箱の操作
    # ------------------------------------------------------------------
    def create(self, thing: str, values: dict, user: User | None, fire: bool = True, check: bool = True) -> Box:
        if thing not in self.fields:
            raise RuleError(f"{thing} という thing はありません")
        vals = {}
        for name, f in self.fields[thing].items():
            if name in values:
                vals[name] = values[name]
            elif f.states:
                flow = self.flows.get((thing, name))
                vals[name] = flow[2][0] if flow else f.states[0]
            elif f.type in self.fields and user is not None:
                vals[name] = user.id      # User を指す項目は、作った人（QUESTIONS_v0.2 R2）
            else:
                vals[name] = ""
        for k in values:
            if k not in self.fields[thing]:
                raise RuleError(f"{thing} に {k} という項目はありません")
        box = Box(thing, f"{thing}-{next(self._ids)}", vals)
        if check and not self.can(user, "create", thing, box):
            raise NotAllowed(f"{user.name if user else '?'} は {thing} を作れません")
        with self._lock:
            self.boxes[thing][box.id] = box
        self._log({"t": "create", "thing": thing, "id": box.id, "values": vals})
        self._changed()
        if fire:
            self.fire(f"{thing} is created", Ctx(user, this=box))
        return box

    def move(self, box: Box, to: str, user: User | None, fire: bool = True) -> None:
        fld = self._state_field(box.thing, to)
        if user is not None and not self.can(user, "move", box.thing, box):
            raise NotAllowed(f"{user.name} はこの {box.thing} を動かせません")
        edges, wins, _ = self.flows.get((box.thing, fld), ([], [], []))
        with box.lock:
            cur = box.values[fld]
            if cur == to:
                return
            can = lambda a, b: (a, b) in edges
            if can(cur, to):
                box.prev[fld] = cur
                box.values[fld] = to
            else:
                prev = box.prev.get(fld)
                if prev is not None and can(prev, to) and can(prev, cur):
                    if (to, cur) in wins:
                        box.values[fld] = to
                    elif (cur, to) in wins:
                        return
                    else:
                        raise RuleError(f"{box.thing}.{fld}: {cur} と {to} がぶつかりました（> がありません）")
                else:
                    raise RuleError(f"{box.thing}.{fld}: {cur} から {to} へは動けません")
            self._log({"t": "set", "thing": box.thing, "id": box.id, "field": fld, "value": box.values[fld]})
        self._changed()
        if fire:
            self.fire(f"{box.thing} moves to {to}", Ctx(user, this=box))

    def update(self, box: Box, values: dict, user: User | None) -> None:
        """状態ではない項目を書き換える。flow で管理する状態は move でしか変えられない（set 禁止）"""
        if user is not None and not self.can(user, "change", box.thing, box):
            raise NotAllowed(f"{user.name} はこの {box.thing} を書き換えられません")
        for k in values:
            f = self.fields[box.thing].get(k)
            if f is None:
                raise RuleError(f"{box.thing} に {k} という項目はありません")
            if f.states:
                raise RuleError(f"{k} は状態なので書き換えられません（move で動かす）")
        with box.lock:
            for k, v in values.items():
                box.values[k] = v
                self._log({"t": "set", "thing": box.thing, "id": box.id, "field": k, "value": v})
        self._changed()

    def _state_field(self, thing: str, state: str) -> str:
        for name, f in self.fields[thing].items():
            if f.states and state in f.states:
                return name
        raise RuleError(f"{thing} に {state} という状態はありません")

    def all(self, thing: str) -> list[Box]:
        with self._lock:
            return list(self.boxes.get(thing, {}).values())

    def find(self, thing: str, values: dict) -> list[Box]:
        return [b for b in self.all(thing) if all(str(b.values.get(k)) == v for k, v in values.items())]

    # ------------------------------------------------------------------
    # list と match
    # ------------------------------------------------------------------
    def _time_of(self, v: str) -> datetime | None:
        try:
            return parse_time(v, self.clock().year)
        except (ValueError, AttributeError):
            return None

    def _where(self, box: Box, cond: str, ctx: Ctx) -> bool:
        cond = cond.strip()
        if cond == "it is me":
            return ctx.user is not None and box.id == ctx.user.id
        m = re.match(r"^(\w+) within (\d+ \w+)$", cond)
        if m:
            t = self._time_of(box.values.get(m.group(1), ""))
            return t is not None and within(t, self.clock(), m.group(2))
        m = re.match(r"^(\w+) is (after|before) now$", cond)
        if m:
            t = self._time_of(box.values.get(m.group(1), ""))
            return t is not None and (t > self.clock() if m.group(2) == "after" else t < self.clock())
        m = re.match(r"^(\w+) is (.+)$", cond)
        if m:
            fld, want = m.group(1), m.group(2).strip()
            if want == "me":
                want = ctx.user.id if ctx.user else None
            elif want.startswith("{") and want.endswith("}"):
                want = ctx.vars.get(want[1:-1])
            else:
                want = unquote(want)
            return str(box.values.get(fld)) == str(want)
        raise RuleError(f"where の書き方が分かりません: '{cond}'")

    def list_items(self, name: str, ctx: Ctx) -> list[Box]:
        lst = self.lists[name]
        src = lst.child("of").text.strip()
        items = self.list_items(src, ctx) if src in self.lists else self.all(src)
        items = [b for b in items if all(self._where(b, w.text, ctx) for w in lst.children_of("where"))]
        if ctx.user is not None:
            items = [b for b in items if self.can(ctx.user, "see", b.thing, b)]
        s = lst.child("sort")
        if s is not None:
            key = s.text.strip()
            items.sort(key=lambda b: (self._time_of(b.values.get(key, "")) or datetime.max, str(b.values.get(key))))
        return items

    def match(self, key: str, value: str) -> str:
        m = self.matches[key]
        default = ""
        for lefts, right, _ in match_arms(m):
            if "else" in lefts:
                default = right
            elif value in lefts:
                return right
        return default

    def match_for(self, thing: str, fld: str, target: str = "color") -> Node | None:
        return self.matches.get(f"{thing}.{fld} to {target}")

    def recipient(self, who: str, box: Box | None, ctx: Ctx) -> User | None:
        """通知の宛先: me ならきっかけの人、項目の名前ならその箱のその項目が指す人"""
        if who == "me":
            return ctx.user
        if box is not None:
            ub = self.boxes.get("User", {}).get(box.values.get(who))
            if ub is not None:
                return User(ub.id, ub.values.get("name", ub.id))
        return None

    def owner_of(self, box: Box) -> User | None:
        """通知の宛先: その箱の User を指す項目（QUESTIONS_v0.2 R3）"""
        for name, f in self.fields[box.thing].items():
            if f.type == "User":
                ub = self.boxes.get("User", {}).get(box.values.get(name))
                if ub is not None:
                    return User(ub.id, ub.values.get("name", ub.id))
        return None

    def label(self, box: Box) -> str:
        """通知などに出す1件の文字（text と日時の項目を並べる）"""
        parts = []
        for name, f in self.fields[box.thing].items():
            if f.type in ("text", "monthday", "date") and box.values.get(name):
                parts.append(str(box.values[name]))
        return " ".join(parts) or box.id

    # ------------------------------------------------------------------
    # 出来事と rule
    # ------------------------------------------------------------------
    def notify(self, rule: str, text: str, user: User | None):
        with self._lock:
            self.notifications.append({"rule": rule, "text": text, "user": user.name if user else None,
                                       "at": self.clock().isoformat(timespec="minutes")})
        self._changed()

    def triggered(self, event: str, ctx: Ctx) -> list[tuple[Node, Ctx]]:
        out = []
        for r in self.rules.values():
            w = r.child("when")
            if w is None:
                continue
            vars_ = self._when_matches(w.text.strip(), event)
            if vars_ is not None:
                c = Ctx(ctx.user, ctx.this, {**ctx.vars, **vars_}, payload=ctx.payload)
                out.append((r, c))
        # relate の >: 同じ出来事で両方動くなら負けた方は動かない
        names = {r.name for r, _ in out}
        losers = {b for a, rel, b, _ in self.relates if rel == ">" and a in names and b in names}
        return [(r, c) for r, c in out if r.name not in losers]

    def _when_matches(self, when: str, event: str) -> dict | None:
        if when == event:
            return {}
        m = re.match(r'^user says "(.*)"$', when)
        e = re.match(r'^user says "(.*)"$', event)
        if m and e:
            pat, names, pos = "^", [], 0
            for v in re.finditer(r"\{(\w+)\}", m.group(1)):
                pat += re.escape(m.group(1)[pos:v.start()]) + "(.+)"
                names.append(v.group(1))
                pos = v.end()
            pat += re.escape(m.group(1)[pos:]) + "$"
            mm = re.match(pat, e.group(1))
            return dict(zip(names, mm.groups())) if mm else None
        return None

    def fire(self, event: str, ctx: Ctx) -> Ctx:
        """出来事を起こす。動いた rule は並列に走る。最後の画面の移動先を ctx.nav に返す。"""
        runs = self.triggered(event, ctx)
        self.run_all(runs)
        for _, c in runs:
            if c.nav:
                ctx.nav = c.nav
        return ctx

    def run_all(self, runs: list[tuple[Node, Ctx]]):
        if self.parallel and len(runs) > 1:
            with ThreadPoolExecutor(max_workers=min(8, len(runs))) as ex:
                list(ex.map(lambda rc: self.run_rule(*rc), runs))
        else:
            for r, c in runs:
                self.run_rule(r, c)

    def _done_key(self, ctx: Ctx):
        return ctx.this if ctx.this is not None else self   # 箱が無ければ全体で1つ

    def run_rule(self, rule: Node, ctx: Ctx):
        holder = self._done_key(ctx)
        done = holder.done if isinstance(holder, Box) else self.__dict__.setdefault("done", set())
        blocked = holder.blocked if isinstance(holder, Box) else self.__dict__.setdefault("blocked", set())
        if rule.name in blocked:
            return
        # before: 前提が済んでいなければ待つ
        for a, rel, b, _ in self.relates:
            if rel == "before" and b == rule.name and a not in done:
                self._pending.append((rule, ctx))
                return
        try:
            for d in rule.children_of("do"):
                self._do(rule, d.text.strip(), ctx)
        except RuleError as e:
            fallbacks = [b for a, rel, b, _ in self.relates if rel == "else" and a == rule.name]
            if not fallbacks:
                self.notify(rule.name, f"うまくいきませんでした: {e}", ctx.user)
                return
            for b in fallbacks:
                self.run_rule(self.rules[b], Ctx(ctx.user, ctx.this, dict(ctx.vars), payload=ctx.payload))
            return
        done.add(rule.name)
        for a, rel, b, _ in self.relates:
            if a != rule.name:
                continue
            if rel == "then" and b in self.rules:
                self.run_rule(self.rules[b], Ctx(ctx.user, ctx.this, dict(ctx.vars), payload=ctx.payload))
            elif rel == "then no":
                blocked.add(b)
        # before 待ちだったものを動かす
        waiting, self._pending = self._pending, []
        for r, c in waiting:
            self.run_rule(r, c)

    def _fill(self, text: str, ctx: Ctx) -> str:
        def rep(m):
            k = m.group(1)
            if k in ctx.vars:
                return str(ctx.vars[k])
            if ctx.this is not None and k in ctx.this.values:
                return str(ctx.this.values[k])
            return m.group(0)
        return re.sub(r"\{(\w+)\}", rep, text)

    def _do(self, rule: Node, text: str, ctx: Ctx):
        m = re.match(r"^notify (\w+) each of (\w+)$", text)
        if m:
            for b in self.list_items(m.group(2), ctx):
                self.notify(rule.name, self.label(b), self.recipient(m.group(1), b, ctx))
            return
        m = re.match(r'^notify (\w+) "(.*)"$', text)
        if m:
            self.notify(rule.name, self._fill(m.group(2), ctx), self.recipient(m.group(1), ctx.this, ctx))
            return
        m = re.match(r"^move this to (\w+)$", text)
        if m:
            if ctx.this is None:
                raise RuleError("this（押された1件）がありません")
            self.move(ctx.this, m.group(1), ctx.user)
            return
        m = re.match(r"^move (\w+) where (.+) to (\w+)$", text)
        if m:
            targets = [b for b in self.all(m.group(1)) if self._where(b, m.group(2), ctx)]
            errors = []

            def one(b):
                try:
                    self.move(b, m.group(3), ctx.user)
                except RuleError as e:
                    errors.append(e)
            if self.parallel and len(targets) > 1:
                with ThreadPoolExecutor(max_workers=min(8, len(targets))) as ex:
                    list(ex.map(one, targets))
            else:
                for b in targets:
                    one(b)
            if errors:
                raise errors[0]
            return
        m = re.match(r"^go (\w+)(?: with this)?$", text)
        if m:
            ctx.nav = m.group(1)
            return
        m = re.match(r"^create (\w+)$", text)
        if m:
            vals = ctx.vars.get("__result") or {}
            ctx.this = self.create(m.group(1), vals if isinstance(vals, dict) else {}, ctx.user)
            return
        if text in self.actions:
            ctx.vars["__result"] = self.run_action(text, ctx)
            return
        words = text.split()
        if words and (words[0], " ".join(words[1:3])) in self.connectors:
            fn = self.connectors[(words[0], " ".join(words[1:3]))]
            result = fn(self._fill(" ".join(words[3:]), ctx))
            if result == "failed":
                raise RuleError(f"{words[0]} {' '.join(words[1:3])} が failed を返しました")
            return
        raise RuleError(f"do の書き方が分かりません: '{text}'")

    # ------------------------------------------------------------------
    # action
    # ------------------------------------------------------------------
    def run_action(self, name: str, ctx: Ctx):
        a = self.actions[name]
        inp = ctx.payload if ctx.payload is not None else ""
        impl = self.action_impls.get(name)
        if impl is not None:
            return impl(inp)
        body = self.bodies.get(name)
        if body is not None:
            from .body import Tagged, input_names, out_states_of
            result = body.run({input_names(a)[0]: inp})
            outs = out_states_of(a)
            if not (isinstance(result, Tagged) and result.state in outs and not outs[result.state]):
                return result
            # 値を持たない状態（missing など）は「決められなかった」→ else へ（QUESTIONS_v0.2 A2）
        els = a.child("else")
        what = els.text.strip() if els else ""
        # 中身（by ai の do）はまだ無い → else の逃げ道へ（QUESTIONS_v0.2 R4）
        if what == "ask user":
            why = "決められませんでした" if name in self.bodies else f"{name} の中身がまだありません"
            self.notify(name, f"確認してください（{why}）: {inp[:60]}", ctx.user)
            return None
        if what == "skip":
            return None
        m = re.match(r"^use default (.+)$", what)
        if m:
            return unquote(m.group(1))
        raise ActionEmpty(f"action {name} の中身がまだありません")

    # ------------------------------------------------------------------
    # 外からの入口
    # ------------------------------------------------------------------
    def tick(self, now: datetime | None = None):
        """時間の出来事。every day at HH:MM / every monday at ... / at 9/24 23:00"""
        now = now or self.clock()
        wd = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][now.weekday()]
        runs = []
        for r in self.rules.values():
            w = r.child("when")
            if w is None:
                continue
            m = re.match(r"^every (\w+) at (\d{1,2}):(\d{2})$", w.text.strip())
            hit = False
            if m and (m.group(1) == "day" or m.group(1) == wd) and (now.hour, now.minute) == (int(m.group(2)), int(m.group(3))):
                hit = True
            m2 = re.match(r"^at (.+)$", w.text.strip())
            if m2:
                t = self._time_of(m2.group(1))
                hit = t is not None and (t.month, t.day, t.hour, t.minute) == (now.month, now.day, now.hour, now.minute)
            key = (r.name, now.strftime("%Y-%m-%d %H:%M"))
            if hit and key not in self._fired_today:
                self._fired_today.add(key)
                runs.append((r, Ctx(None)))
        names = {r.name for r, _ in runs}
        losers = {b for a, rel, b, _ in self.relates if rel == ">" and a in names and b in names}
        self.run_all([(r, c) for r, c in runs if r.name not in losers])

    def says(self, user: User, text: str) -> Ctx:
        return self.fire(f'user says "{text}"', Ctx(user))

    def tap(self, user: User, button: str, on: str, box_id: str | None = None) -> Ctx:
        box = None
        if box_id:
            for t in self.boxes.values():
                if box_id in t:
                    box = t[box_id]
        ctx = self.fire(f"user taps {button} on {on}", Ctx(user, this=box))
        if box is not None and box.thing != on:        # thing の名前で書いた rule も動く（QUESTIONS_v0.2 U2）
            c2 = self.fire(f"user taps {button} on {box.thing}", Ctx(user, this=box))
            ctx.nav = ctx.nav or c2.nav
        return ctx

    def drag(self, user: User, box_id: str, to: str) -> None:
        """board でカードを別の列へ動かした → move の出来事（flow と who が守られる）"""
        for t in self.boxes.values():
            if box_id in t:
                self.move(t[box_id], to, user)
                return
        raise RuleError(f"{box_id} が見つかりません")

    def gives(self, connect: str, event: str, payload: str) -> Ctx:
        return self.fire(f"{connect} gives {event}", Ctx(None, payload=payload))

    def submit(self, user: User, input_name: str, values: dict) -> Box:
        """input を送る。input と同じ名前の thing ではなく、input の項目を持つ thing を作る。"""
        thing = self.input_thing(input_name)
        return self.create(thing, values, user)

    def input_thing(self, input_name: str) -> str:
        inp = next(i for i in self.spec.decls("input") if i.name == input_name)
        names = {c.keyword for c in inp.children}
        for t, fs in self.fields.items():
            if names <= set(fs):
                return t
        raise RuleError(f"input {input_name} の項目を持つ thing がありません")
