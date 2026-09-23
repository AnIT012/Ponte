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

import functools
import itertools
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .parser import Node, Spec, flow_parts, flow_states, match_arms, relate_lines, thing_fields
from .values import parse_time, unquote, within


class RuleError(Exception):
    """rule がやり遂げられなかった（relate の else に進む）"""


class NoResult(Exception):
    """result を使う rule の前で、action が答えを出さなかった"""


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
    last_move: tuple | None = None                    # 直前の move（項目, 前, 後, した人の id）。1回だけ取り消せる


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


@functools.lru_cache(maxsize=1024)
def _parse_cond(cond: str) -> tuple[str, str | None, str | None]:
    """where の1行を読む（同じ行は1回だけ読む。一覧は箱の数だけ同じ where を見るので）"""
    cond = cond.strip()
    if cond == "it is me":
        return "me", None, None
    if cond == "it is not me":
        return "not me", None, None
    m = re.match(r"^(\w+) within (\d+ \w+)$", cond)
    if m:
        return "within", m.group(1), m.group(2)
    m = re.match(r"^(\w+) is (after|before) now$", cond)
    if m:
        return m.group(2), m.group(1), None
    m = re.match(r"^(\w+) is (.+)$", cond)
    if m:
        return "is", m.group(1), m.group(2).strip()
    return "?", None, None


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
        self.ask_client = None            # ask ai で使う AI（テストでは差し替える。None なら API キーで呼ぶ）
        self._pending: list[tuple[Node, Ctx]] = []   # before 待ちの rule
        self._fired_today: set = set()
        self.trace: list[tuple] = []      # 起きたこと（("move", thing, 項目, 前, 後) / ("rule", 名前)）。ponte test の穴さがしに使う
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
            self._migrate()

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

    def _migrate(self):
        """change の通りに、古い形のデータを今の形にする（足した項目の初期値・名前の変更・消した項目・消した状態の移し先）"""
        for ch in self.spec.decls("change"):
            thing = ch.name
            for b in self.all(thing):
                for c in ch.children:
                    t = c.text.strip()
                    if c.keyword == "add":
                        m = re.match(r"^(\w+)\s+.+?=\s*(.*)$", t)
                        if m and m.group(1) not in b.values:
                            b.values[m.group(1)] = unquote(m.group(2))
                    elif c.keyword == "rename":
                        m = re.match(r"^(\w+)\s+to\s+(\w+)$", t)
                        if m and m.group(1) in b.values:
                            b.values[m.group(2)] = b.values.pop(m.group(1))
                    elif c.keyword == "remove":
                        m = re.match(r"^state\s+(\w+)\s*->\s*(\w+)$", t)
                        if m:
                            for k, v in b.values.items():
                                if v == m.group(1):
                                    b.values[k] = m.group(2)
                        elif re.fullmatch(r"\w+", t):
                            b.values.pop(t, None)
            for b in self.all(thing):          # 残りの足りない項目は空に
                for k in self.fields.get(thing, {}):
                    b.values.setdefault(k, "")

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
        """User 箱を名前で探す。無ければ作る。
        thing User に role[...] があれば、その値が役割になる（who の `admin can ...` の admin）。"""
        if "User" in self.fields:
            b = next((x for x in self.boxes["User"].values() if x.values.get("name") == name), None)
            if b is None:
                b = self.create("User", {"name": name}, user=None, fire=False, check=False)
            return User(b.id, name, roles or self.roles_of(b))
        return User(name, name, roles or {"user"})

    def roles_of(self, b: Box) -> set:
        f = self.fields["User"].get("role")
        return {"user", b.values["role"]} if f is not None and f.states and b.values.get("role") else {"user"}

    def set_role(self, name: str, role: str) -> None:
        """役割を直接決める（最初の管理者を決める時だけ。`ponte role`）。flow と who は通さない"""
        f = self.fields.get("User", {}).get("role")
        if f is None or not f.states:
            raise RuleError("thing User に role[...] がありません（例: role[member | admin]）")
        if role not in f.states:
            raise RuleError(f"{role} という役割はありません（{' / '.join(f.states)}）")
        b = self.boxes["User"][self.login(name).id]
        with b.lock:
            b.values["role"] = role
            self._log({"t": "set", "thing": "User", "id": b.id, "field": "role", "value": role})
        self._changed()

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
            before = cur
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
            box.last_move = (fld, before, box.values[fld], user.id if user else None)
            self.trace.append(("move", box.thing, fld, before, box.values[fld]))
        self._changed()
        if fire:
            self.fire(f"{box.thing} moves to {to}", Ctx(user, this=box))

    def undo(self, box: Box, user: User) -> str:
        """直前の1回の move だけを取り消す。した本人だけ。flow の矢印は増やさない。
        move で起きた出来事（通知など）は取り消さない。"""
        with box.lock:
            lm = box.last_move
            if lm is None:
                raise RuleError("取り消せる変更がありません（取り消せるのは直前の1回だけ）")
            fld, before, after, who = lm
            if who != user.id or box.values.get(fld) != after:
                raise RuleError("取り消せるのは、自分がした直前の1回だけです")
            box.values[fld] = before
            box.prev[fld] = None
            box.last_move = None
            self._log({"t": "set", "thing": box.thing, "id": box.id, "field": fld, "value": before})
        self._changed()
        return before

    def remove(self, box: Box, user: User | None, fire: bool = True, _seen: set | None = None) -> None:
        """箱を消す。この箱を指している項目は gone[...] の通りにする（remove too / leave empty / block）"""
        seen = _seen if _seen is not None else set()
        if box.id in seen:
            return
        seen.add(box.id)
        if user is not None and not self.can(user, "remove", box.thing, box):
            raise NotAllowed(f"{user.name} はこの {box.thing} を消せません")
        pointing = []
        for t, fs in self.fields.items():
            for name, f in fs.items():
                target = f.type[len("list of "):] if f.type.startswith("list of ") else f.type
                if target != box.thing:
                    continue
                for b in self.all(t):
                    if b.values.get(name) == box.id:
                        pointing.append((b, name, f.gone or "block"))
        blocked = [(b, n) for b, n, g in pointing if g == "block"]
        if blocked:
            b, n = blocked[0]
            raise RuleError(f"{b.thing}.{n} がこの {box.thing} を指しているので消せません（gone[block]）")
        with self._lock:
            self.boxes[box.thing].pop(box.id, None)
        self._log({"t": "remove", "thing": box.thing, "id": box.id})
        for b, n, g in pointing:
            if g == "remove too":
                self.remove(b, None, fire=fire, _seen=seen)
            elif g == "leave empty":
                with b.lock:
                    b.values[n] = ""
                self._log({"t": "set", "thing": b.thing, "id": b.id, "field": n, "value": ""})
        self._changed()
        if fire:
            self.fire(f"{box.thing} is removed", Ctx(user, this=box))

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
        kind, fld, arg = _parse_cond(cond)
        if kind == "me":
            return ctx.user is not None and box.id == ctx.user.id
        if kind == "not me":
            return ctx.user is None or box.id != ctx.user.id
        if kind == "within":
            t = self._time_of(box.values.get(fld, ""))
            return t is not None and within(t, self.clock(), arg)
        if kind in ("after", "before"):
            t = self._time_of(box.values.get(fld, ""))
            return t is not None and (t > self.clock() if kind == "after" else t < self.clock())
        if kind == "is":
            want = arg
            if want == "me":
                want = ctx.user.id if ctx.user else None
            elif want.startswith("{") and want.endswith("}"):
                want = ctx.vars.get(want[1:-1])
            else:
                want = unquote(want)
            return str(box.values.get(fld)) == str(want)
        raise RuleError(f"where の書き方が分かりません: '{cond.strip()}'")

    def list_items(self, name: str, ctx: Ctx) -> list[Box]:
        lst = self.lists[name]
        src = lst.child("of").text.strip()
        items = self.list_items(src, ctx) if src in self.lists else self.all(src)
        items = [b for b in items if all(self._where(b, w.text, ctx) for w in lst.children_of("where"))]
        if ctx.user is not None:
            items = [b for b in items if self.can(ctx.user, "see", b.thing, b)]
        s = lst.child("sort")
        if s is not None:
            words = s.text.split()
            key, desc = words[0], len(words) > 1 and words[1] == "desc"      # sort deadline desc で新しい順
            items.sort(key=lambda b: (self._time_of(b.values.get(key, "")) or datetime.max, str(b.values.get(key))), reverse=desc)
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

    def applies(self, rule: Node, ctx: Ctx) -> bool:
        """rule の where（押された1件の条件）を全部満たすか"""
        ws = rule.children_of("where")
        if not ws:
            return True
        return ctx.this is not None and all(self._where(ctx.this, w.text, ctx) for w in ws)

    def run_rule(self, rule: Node, ctx: Ctx):
        holder = self._done_key(ctx)
        done = holder.done if isinstance(holder, Box) else self.__dict__.setdefault("done", set())
        blocked = holder.blocked if isinstance(holder, Box) else self.__dict__.setdefault("blocked", set())
        if rule.name in blocked:
            return
        if not self.applies(rule, ctx):     # rule の where に合わない時は、その rule は起きない
            return
        # before: 前提が済んでいなければ待つ
        for a, rel, b, _ in self.relates:
            if rel == "before" and b == rule.name and a not in done:
                self._pending.append((rule, ctx))
                return
        self.trace.append(("rule", rule.name))
        try:
            for d in rule.children_of("do"):
                self._do(rule, d.text.strip(), ctx, d)
        except NoResult:            # 前の action が答えを出さなかった（skip など）→ この rule は静かに起きない
            return
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
                c2 = Ctx(ctx.user, ctx.this, dict(ctx.vars), payload=ctx.payload)
                self.run_rule(self.rules[b], c2)
                ctx.nav = c2.nav or ctx.nav
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
                ref = self._ref(ctx.this, k)
                return self.label(ref) if ref is not None else str(ctx.this.values[k])
            return m.group(0)
        return re.sub(r"\{(\w+)\}", rep, text)

    def _ref(self, box: Box, fld: str) -> Box | None:
        """box の項目 fld が別の thing を指していれば、その箱"""
        f = self.fields[box.thing].get(fld)
        if f is None or f.type not in self.fields:
            return None
        return self.boxes[f.type].get(box.values.get(fld))

    def _target(self, ref: str, ctx: Ctx) -> Box:
        """`this` か `項目 of this`（this が指している箱）"""
        if ctx.this is None:
            raise RuleError("this（押された1件）がありません")
        if ref == "this":
            return ctx.this
        m = re.match(r"^(\w+) of this$", ref)
        b = self._ref(ctx.this, m.group(1)) if m else None
        if b is None:
            raise RuleError(f"{ref} が見つかりません")
        return b

    def value_of(self, expr: str, ctx: Ctx) -> str:
        """create の下の値：this / me / "文字" / 7 days from now / {名前} / 項目 of this"""
        e = expr.strip()
        if e == "this" or re.fullmatch(r"\w+ of this", e):
            return self._target(e, ctx).id if e == "this" else (ctx.this.values.get(e.split()[0]) if ctx.this else "")
        if e == "me":
            if ctx.user is None:
                raise RuleError("me（押した人）がいません")
            return ctx.user.id
        m = re.fullmatch(r"(\d+) (minutes?|hours?|days?|weeks?) from now", e)
        if m:
            n, unit = int(m.group(1)), m.group(2).rstrip("s")
            t = self.clock() + timedelta(**{unit + "s": n})
            return f"{t.year}/{t.month}/{t.day} {t.hour}:{t.minute:02d}"   # 年まで書く（推測しない）
        if e.startswith("{") and e.endswith("}"):
            return str(ctx.vars.get(e[1:-1], ""))
        if e == "result":                              # 直前の action の答え（relate の then で次の rule へ渡る）
            r = ctx.vars.get("__result")
            if r is None:
                raise NoResult()
            return str(getattr(r, "value", None) if getattr(r, "value", None) is not None else r)
        return unquote(e)

    def _do(self, rule: Node, text: str, ctx: Ctx, node: Node | None = None):
        m = re.match(r"^notify (\w+) each of (\w+)$", text)
        if m:
            for b in self.list_items(m.group(2), ctx):
                self.notify(rule.name, self.label(b), self.recipient(m.group(1), b, ctx))
            return
        m = re.match(r'^notify (\w+) "(.*)"$', text)
        if m:
            self.notify(rule.name, self._fill(m.group(2), ctx), self.recipient(m.group(1), ctx.this, ctx))
            return
        m = re.match(r"^move (this|\w+ of this) to (\w+)$", text)
        if m:
            self.move(self._target(m.group(1), ctx), m.group(2), ctx.user)
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
        if text == "remove this":
            if ctx.this is None:
                raise RuleError("this（押された1件）がありません")
            self.remove(ctx.this, ctx.user)
            return
        m = re.match(r"^set (\w+) to (.+)$", text)
        if m:
            if ctx.this is None:
                raise RuleError("this（押された1件）がありません")
            self.update(ctx.this, {m.group(1): self.value_of(m.group(2), ctx)}, ctx.user)
            return
        m = re.match(r"^(\w+) with (\w+)$", text)
        if m and m.group(1) in self.actions:           # action の入力を、this の項目から
            if ctx.this is None:
                raise RuleError("this（押された1件）がありません")
            c2 = Ctx(ctx.user, ctx.this, ctx.vars, payload=str(ctx.this.values.get(m.group(2), "")))
            ctx.vars["__result"] = self.run_action(m.group(1), c2)
            return
        m = re.match(r"^go (\w+)(?: with this)?$", text)
        if m:
            ctx.nav = m.group(1)
            return
        m = re.match(r"^create (\w+)$", text)
        if m:
            vals = ctx.vars.get("__result") or {}
            vals = dict(vals) if isinstance(vals, dict) else {}
            for c in (node.children if node is not None else []):     # 下に「項目 値」
                vals[c.keyword] = self.value_of(c.text, ctx)
            ctx.this = self.create(m.group(1), vals, ctx.user)
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
        """how の limit（時間）と on failure retry（やり直す回数）を守って、中身を呼ぶ"""
        a = self.actions[name]
        how = a.child("how")
        limit, retry = None, 0
        for h in (how.children if how else []):
            m = re.match(r"^limit\s+(\d+(?:\.\d+)?)\s+seconds?$", h.raw)
            if m:
                limit = float(m.group(1))
            m = re.match(r"^on failure retry (\d+) times?$", h.raw)
            if m:
                retry = int(m.group(1))
        last = None
        for _ in range(retry + 1):
            try:
                if limit is None:
                    return self._run_action_once(name, ctx)
                with ThreadPoolExecutor(max_workers=1) as ex:
                    return ex.submit(self._run_action_once, name, ctx).result(timeout=limit)
            except ActionEmpty:
                raise
            except Exception as e:      # noqa: BLE001  時間切れ・中身の失敗 → やり直す
                last = e
        raise RuleError(f"action {name} が{retry + 1}回とも失敗しました: {last}")

    def _run_action_once(self, name: str, ctx: Ctx):
        a = self.actions[name]
        inp = ctx.payload if ctx.payload is not None else ""
        ask = a.child("ask")
        if ask is not None and ask.text.strip() == "ai" and name not in self.action_impls:
            result = self.ask_ai(a, inp)
            if result is not None:
                return result
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

    def ask_ai(self, a: Node, inp: str):
        """ask ai: 実行の度にAIに聞く。答えが out の形でなければ使わない（else へ）。キーが無ければ else へ"""
        from .body import Tagged, out_states_of, parse_expected
        from .fill import AnthropicHTTP, action_source
        try:
            ai = self.ask_client or AnthropicHTTP()
        except RuntimeError:
            return None
        prompt = ("次の契約の action の答えを1行だけ返してください。形は out の通り（例と同じ形）。説明は要りません。\n\n"
                  + action_source(self.spec, a) + f"\n入力: {inp}\n")
        reply = ai([{"role": "user", "content": prompt}]).strip().splitlines()
        if not reply:
            return None
        outs = out_states_of(a)
        got = parse_expected(reply[0].strip().strip("`"), outs)
        if outs and not (isinstance(got, Tagged) and got.state in outs):
            return None
        if isinstance(got, Tagged) and not outs.get(got.state):
            return got
        return got

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
            if box is None or (user is not None and not any(self.can(user, a, box.thing, box) for a in ("see", "change", "move", "remove"))):
                raise NotAllowed("見つかりません")          # 何の権利も無い箱のボタンは押せない（あるかどうかも言わない）
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
