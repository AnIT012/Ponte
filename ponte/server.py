"""画面を動かす（仕様 v0.2 6章）。Python 標準の http.server と、素の HTML / CSS / JavaScript だけ。

  python -m ponte run spec/hub_app.ponte --port 8000

サーバーは scene / look / part / input / style / words を読んで「何を見せるか」を JSON にする。
描くのはブラウザ。画面の状態（タブ・メニューの開閉）はブラウザが持ち、見せる時にサーバーへ渡す。
箱が変わると開いている画面へ「変わった」を送る（Server-Sent Events）。
"""
from __future__ import annotations

import html as _html
import json
import pkgutil
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .auth import COOKIE, SESSION_SECONDS, Sessions, Users, cookie_token, login_page
from .body import Body, BodyError
from .parser import Node, Spec, match_arms, parse_button, states_of, words_entries
from .runtime import Box, Ctx, Engine, RuleError
from .values import parse_time

PALETTE = {
    "red": "#E5484D", "gray": "#8B8D98", "blue": "#3E63DD", "green": "#30A46C", "orange": "#F76B15",
    "yellow": "#E2A336", "purple": "#8E4EC6", "pink": "#D6409F", "teal": "#12A594", "black": "#1C2024",
}
AUTO = ["#3E63DD", "#30A46C", "#F76B15", "#8E4EC6", "#12A594", "#D6409F", "#E2A336", "#8B8D98"]
KINDS = {"cards", "list", "table", "board", "calendar", "chart", "detail", "dialog", "sheet"}


def color_of(name: str | None, fallback_index: int = 0) -> str:
    if not name:
        return AUTO[fallback_index % len(AUTO)]
    return PALETTE.get(name, name if name.startswith("#") else AUTO[fallback_index % len(AUTO)])


class Env:
    """1回の「見せる」に必要なもの"""
    def __init__(self, user, scene: str, state: dict, this: Box | None, origin: str | None, lang: str):
        self.user, self.scene, self.state, self.this, self.origin, self.lang = user, scene, state, this, origin, lang
        self.ctx = Ctx(user, this=this)


class App:
    def __init__(self, spec: Spec, engine: Engine):
        self.spec, self.eng = spec, engine
        self.auth = None                          # ponte run --login の時だけ
        self.version = 0                          # ponte run --reload で読み直すたびに増える
        self._press_cache: dict = {}
        self._card_cache: dict = {}
        self._local = threading.local()           # 見ている人は要求ごと（サーバーは並列に動くので、App に直接持たない）
        self.scenes = {s.name: s for s in spec.decls("scene")}
        self.looks = {l.name: l for l in spec.decls("look")}
        self.parts = {p.name: p for p in spec.decls("part")}
        self.inputs = {i.name: i for i in spec.decls("input")}
        self.words = {w.name: words_entries(w) for w in spec.decls("words")}
        self.home = next(iter(self.scenes), None)
        self.part_bodies = {}
        for name, p in self.parts.items():
            do = p.child("do")                                   # 部品の中の計算は do の下（action と同じ）
            lines = list(do.children) if do is not None else []
            in_ = p.child("in")
            self.part_bodies[name] = Body(p, {}, [in_.text.split()[0]] if in_ else [], {}, single_result=False, lines=lines)

    # ------------------------------------------------------------------
    BUILTIN = {"search": "さがす", "save": "保存", "cancel": "キャンセル", "none": "まだありません", "more": "もっと見る", "undo": "取り消す",
               "next-year": "来年（{year}年）の締切ですか？ いいえなら、もう過ぎた締切として保存します", "total-of": "{x}の合計"}   # 言語が出す文字（words で訳せる）
    BUILTIN_EN = {"search": "Search", "save": "Save", "cancel": "Cancel", "none": "Nothing yet", "more": "Show more", "undo": "Undo",
                  "total-of": "Total {x}"}

    def reload(self, spec: Spec, engine: Engine) -> None:
        """書き直した spec に入れ替える（--reload）。開いている画面には読み直してもらう"""
        old, auth, version = self.eng, self.auth, self.version
        self.__init__(spec, engine)
        self.auth, self.version = auth, version + 1
        for fn in list(old.listeners):
            fn()

    def tr(self, key, env: Env) -> str:
        key = "" if key is None else str(key)
        builtin = self.BUILTIN_EN if env.lang == "en" else self.BUILTIN
        return self.words.get(env.lang, {}).get(key, builtin.get(key, self.BUILTIN.get(key, key)))

    def scene_states(self, scene: Node) -> dict:
        out = {}
        for c in scene.children:
            if c.text.startswith("["):
                vals = states_of(c.text)
                init = c.text.split("=", 1)[1].strip() if "=" in c.text else vals[0]
                out[c.keyword] = {"values": vals, "init": init}
        return out

    def view(self, scene: str, user, state: dict, this_id: str | None, origin: str | None, lang: str) -> dict:
        this = None
        if this_id:
            for t in self.eng.boxes.values():
                if this_id in t:
                    this = t[this_id]
        env = Env(user, scene, dict(state), this, origin, lang)
        self._viewer = user.name if user is not None else "me"
        self._local.user = user
        if scene in self.inputs:
            top = []  # noqa
            if self.home in self.scenes:
                top = [self.part_block(self.parts[c.text.strip()], None, env) for c in self.scenes[self.home].children
                       if c.keyword == "top" and c.text.strip() in self.parts]
            return {"scene": scene, "states": {}, "slots": [{"slot": "top", "blocks": top}, {"slot": "main", "blocks": [self.input_block(scene, env)]}]}
        s = self.scenes.get(scene)
        if s is None:
            return {"scene": scene, "states": {}, "slots": [], "error": f"{scene} という画面はありません"}
        states = self.scene_states(s)
        for k, v in states.items():
            if env.state.get(k) not in v["values"]:
                env.state[k] = v["init"]
        slots: dict[str, list] = {}
        order = []
        for c in s.children:
            if c.text.startswith("["):
                continue
            if c.keyword not in slots:
                slots[c.keyword] = []
                order.append(c.keyword)
            slots[c.keyword] += self.content(c.text, c, env)
        return {"scene": scene, "states": {k: {"values": v["values"], "current": env.state[k],
                                                 "labels": {x: self.tr(x, env) for x in v["values"]}} for k, v in states.items()},
                "slots": [{"slot": k, "blocks": slots[k]} for k in order]}

    # ------------------------------------------------------------------
    def content(self, text: str, node: Node, env: Env, match_state: str | None = None) -> list[dict]:
        text = (text or "").strip()
        if not text or text == "nothing":
            return []
        m = re.match(r"^match (.+)$", text)
        if m:
            subj = m.group(1).strip()
            value = env.state.get(subj) if subj in env.state else self.eval_value(subj, env)
            chosen = None
            for lefts, right, _ in match_arms(node):
                if str(value) in lefts:
                    chosen = right
                    break
                if "else" in lefts and chosen is None:
                    chosen = right
            if chosen is None:
                return []
            return self.content(chosen, node, env, subj if subj in env.state else None)
        m = re.match(r"^tabs (\w+)$", text)
        if m:
            name = m.group(1)
            sc = self.scenes[env.scene]
            vals = self.scene_states(sc).get(name, {}).get("values", [])
            return [{"type": "tabs", "state": name, "current": env.state.get(name),
                     "options": [{"value": v, "label": self.tr(v, env), "icon": self.icon_for(name, v)} for v in vals]}]
        if text.startswith("button "):   # 画面の下のボタンだけ目立たせる。上のボタンは控えめ
            pb = parse_button(text[7:])
            return [self.button(pb, env, main=(node.keyword == "bottom"), on=env.scene)] if self.can_open(pb["id"], env.scene) else []
        if text == "notices":
            return [{"type": "notices"}]
        if text.startswith("stats "):    # stats Late, MyLoans, sum price of Orders … 件数と合計を並べる
            return [{"type": "stats", "items": [self.stat(x.strip(), env) for x in text[6:].split(",")]}]
        m = re.match(r"^(\w+) as (\w+)$", text)
        if m:
            name, kind = m.group(1), m.group(2)
            if kind in ("dialog", "sheet"):
                inner = self.part_block(self.parts[name], None, env) if name in self.parts else {"type": "text", "text": name}
                close = None
                if match_state:
                    vals = self.scene_states(self.scenes[env.scene])[match_state]["values"]
                    close = {"state": match_state, "value": next((v for v in vals if v != env.state.get(match_state)), vals[0])}
                return [{"type": "dialog", "kind": kind, "blocks": [inner], "close": close}]
            if name == "this":
                return [self.detail_block(env)] if env.this is not None else [{"type": "empty", "text": "選ばれたものがありません"}]
            return [self.collection(name, kind, env)]
        if text in self.parts:
            return [self.part_block(self.parts[text], None, env)]
        return [{"type": "text", "text": self.tr(text, env)}]

    def eval_value(self, expr: str, env: Env):
        m = re.match(r"^count of (\w+)$", expr.strip())
        if m:
            return len(self.source(m.group(1), env))
        return expr

    def source(self, name: str, env: Env) -> list[Box]:
        if name in self.eng.lists:
            return self.eng.list_items(name, env.ctx)
        items = self.eng.all(name)
        if env.user is not None:
            items = [b for b in items if self.eng.can(env.user, "see", name, b)]
        return items

    def thing_of(self, name: str) -> str:
        while name in self.eng.lists:
            name = self.eng.lists[name].child("of").text.strip()
        return name

    # ------------------------------------------------------------------
    def button(self, pb: dict, env: Env, main: bool, on: str) -> dict:
        tone = pb["tone"] or ("main" if main else "quiet")      # 強さはボタンの行に書く（書かなければ最初のボタンだけ強い）
        b = {"type": "button", "id": pb["id"], "label": self.tr(pb["label"] or pb["id"], env), "tone": tone, "on": on,
             "icon": pb["icon"], "confirm": self.tr(pb["confirm"], env) if pb["confirm"] else None}
        if pb["act"]:
            b["act"] = pb["act"]
        return b

    def icon_for(self, subject: str, value) -> str | None:
        """match 〇〇 to icon があれば、その値のアイコン"""
        for m in self.eng.matches.values():
            if m.text == f"{subject} to icon":
                for lefts, right, _ in match_arms(m):
                    if str(value) in lefts or "else" in lefts:
                        return right
        return None

    def stat(self, item: str, env: Env) -> dict:
        """`一覧` → 件数 / `sum 項目 of 一覧` → 合計（見えるものだけ数える）"""
        m = re.fullmatch(r"sum (\w+) of (\w+)", item)
        name = m.group(2) if m else item
        rows = self.eng.list_items(name, env.ctx)
        if not m:
            return {"label": self.tr(name, env), "value": f"{len(rows):,}", "list": name}
        total = 0
        for b in rows:
            v = str(b.values.get(m.group(1), "")).replace(",", "")
            n = re.match(r"-?\d+(?:\.\d+)?", v)
            total += float(n.group(0)) if n else 0
        total = int(total) if total == int(total) else round(total, 2)
        return {"label": self.tr("total-of", env).replace("{x}", self.tr(m.group(1), env)), "value": f"{total:,}", "list": name}

    def can_open(self, bid: str, on: str) -> bool:
        """画面のボタンが入力（input）を開くなら、その thing を作れる人にだけ見せる（押しても保存できないので）"""
        me = self.eng.login(self._viewer)
        for r in self.eng.rules.values():
            w = r.child("when")
            if w is None or w.text.strip() != f"user taps {bid} on {on}":
                continue
            for d in r.children_of("do"):
                m = re.match(r"^go (\w+)", d.text.strip())
                if m and self.spec.find("input", m.group(1)) and not self.eng.can(me, "create", self.eng.input_thing(m.group(1)), None):
                    return False
        return True

    def _press_rules(self, bid: str, on: str, thing: str) -> list:
        """そのボタンを押した時に動く rule（一覧の行ごとに聞かれるので、組み合わせごとに1回だけ探す）"""
        key = (bid, on, thing)
        if key not in self._press_cache:
            pat = re.compile(rf"^user taps {re.escape(bid)} on ({re.escape(on)}|{re.escape(thing)})$")
            self._press_cache[key] = [r for r in self.eng.rules.values()
                                      if r.child("when") is not None and pat.match(r.child("when").text.strip())]
        return self._press_cache[key]

    @property
    def _viewer(self) -> str:
        return getattr(self._local, "name", "me")

    @_viewer.setter
    def _viewer(self, name: str) -> None:
        self._local.name = name
        self._local.user = None

    def _viewer_user(self):
        if getattr(self._local, "user", None) is None:
            self._local.user = self.eng.login(self._viewer)
        return self._local.user

    def can_press(self, box: Box, bid: str, on: str) -> bool:
        """このボタンの rule が `move this to X` なら、flow でいま X へ動けるかを見る（動けないボタンは押せなくする）"""
        for r in self._press_rules(bid, on, box.thing):
            viewer = self._viewer_user()
            if not self.eng.applies(r, Ctx(viewer, this=box)):   # rule の where に合わない
                return False
            for d in r.children_of("do"):
                if d.text.strip() == "remove this":         # 消すボタンは、who で消せる時だけ押せる
                    if not self.eng.can(viewer, "remove", box.thing, box):
                        return False
                    continue
                m = re.match(r"^move this to (\w+)$", d.text.strip())
                if not m:
                    continue
                to = m.group(1)
                fld = next((k for k, f in self.eng.fields[box.thing].items() if f.states and to in f.states), None)
                if fld is None:
                    return False
                edges, wins, _ = self.eng.flows.get((box.thing, fld), ([], [], []))
                cur = box.values.get(fld)
                prev = box.prev.get(fld)
                ok = (cur, to) in edges or ((to, cur) in wins and prev is not None and (prev, to) in edges)
                if not ok:
                    return False
        return True

    def state_field(self, thing: str) -> str | None:
        return next((k for k, f in self.eng.fields.get(thing, {}).items() if f.states), None)

    def mark_of(self, box: Box, fld: str, env: Env) -> dict:
        v = box.values.get(fld, "")
        mt = self.eng.match_for(box.thing, fld)
        states = self.eng.fields[box.thing][fld].states or []
        idx = states.index(v) if v in states else 0
        return {"label": self.tr(v, env), "value": v, "color": color_of(self.eng.match(mt.text, v) if mt else None, idx),
                "icon": self.icon_for(f"{box.thing}.{fld}", v)}

    def show_value(self, box: Box, fld: str, env: Env):
        f = self.eng.fields[box.thing].get(fld)
        v = box.values.get(fld, "")
        if f is not None and f.type in self.eng.fields and v:
            ub = self.eng.boxes.get(f.type, {}).get(v)
            return ub.values.get("name", v) if ub else v
        if f is not None and f.type in ("number", "money") and re.fullmatch(r"-?\d+", str(v)):
            return f"{int(v):,}"                       # 数は3けたごとに区切る
        return self.tr(v, env) if f is not None and f.states else v

    def has_card_rule(self, name: str) -> bool:
        if name not in self._card_cache:
            self._card_cache[name] = bool(self._press_rules("card", name, self.thing_of(name)))
        return self._card_cache[name]

    def row(self, box: Box, look: Node | None, env: Env, list_name: str) -> dict:
        fields = self.eng.fields[box.thing]
        texts = [k for k, f in fields.items() if f.type in ("text", "monthday", "date")]
        sf = self.state_field(box.thing)
        row = {"id": box.id, "buttons": [], "values": {k: self.show_value(box, k, env) for k in fields}}
        if look is None:
            row["title"] = box.values.get(texts[0], "") if texts else box.id
            if len(texts) > 1:
                row["sub"] = {"text": " · ".join(str(box.values.get(k, "")) for k in texts[1:])}
            if sf:
                row["mark"] = self.mark_of(box, sf, env)
        else:
            nb = 0
            for c in look.children:
                if c.keyword == "title":
                    row["title"] = self.show_value(box, c.text.strip(), env)
                elif c.keyword == "sub":
                    m = re.match(r"^(\w+) of (\w+)$", c.text.strip())
                    if m and m.group(1) in self.parts:
                        row["sub"] = self.part_block(self.parts[m.group(1)], box.values.get(m.group(2)), env)
                    else:
                        row["sub"] = {"text": self.show_value(box, c.text.strip(), env)}
                elif c.keyword == "mark":
                    m = re.match(r"^color of (\w+)$", c.text.strip())
                    row["mark"] = self.mark_of(box, m.group(1) if m else c.text.strip(), env)
                elif c.keyword == "lead":
                    t = str(self.show_value(box, c.text.strip(), env) or "?")
                    row["lead"] = {"text": t[:1].upper(), "color": AUTO[sum(map(ord, t)) % len(AUTO)]}
                elif c.keyword == "button":
                    pb = parse_button(c.text.strip())
                    b = self.button(pb, env, main=(nb == 0), on=list_name)
                    if not b.get("act") and not self.can_press(box, pb["id"], list_name):
                        b["disabled"] = True
                        b["tone"] = "quiet"
                    row["buttons"].append(b)
                    nb += 1
        row["cardTap"] = self.has_card_rule(list_name)
        return row

    def collection(self, name: str, kind: str, env: Env) -> dict:
        boxes = self.source(name, env)
        thing = self.thing_of(name)
        look = self.looks.get(name)
        fields = self.eng.fields.get(thing, {})
        sf = self.state_field(thing)
        base = {"name": name, "look": name, "kind": kind}
        if kind == "board":
            states = self.eng.flows.get((thing, sf), (None, None, fields[sf].states if sf else []))[2] if sf else []
            cols = []
            for i, st in enumerate(states):
                mt = self.eng.match_for(thing, sf)
                cols.append({"state": st, "label": self.tr(st, env), "color": color_of(self.eng.match(mt.text, st) if mt else None, i),
                             "rows": [self.row(b, look, env, name) for b in boxes if b.values.get(sf) == st]})
            return {**base, "type": "board", "columns": cols, "draggable": (thing, sf) in self.eng.flows}
        if kind == "chart":
            # 分け方は `group by 項目`（無ければ状態）。高さは件数か、`sum 項目` の合計
            gb = look.child("group") if look is not None else None
            gf = gb.text[3:].strip() if gb is not None and gb.text.startswith("by ") else sf
            sm = look.child("sum") if look is not None else None
            sum_f = sm.text.strip() if sm is not None else None
            states = (fields[gf].states or []) if gf in fields else []
            keys = states or list(dict.fromkeys(str(self.show_value(b, gf, env)) for b in boxes if gf and b.values.get(gf) not in (None, "")))

            def amount(b):
                if not sum_f:
                    return 1
                n = re.match(r"-?\d+(?:\.\d+)?", str(b.values.get(sum_f, "")).replace(",", ""))
                return float(n.group(0)) if n else 0
            key_of = (lambda b: b.values.get(gf)) if states else (lambda b: str(self.show_value(b, gf, env)))
            mt = self.eng.match_for(thing, gf) if states else None
            fmt = lambda x: f"{int(x):,}" if x == int(x) else f"{x:,.2f}"
            bars = []
            for i, k in enumerate(keys):
                v = sum(amount(b) for b in boxes if key_of(b) == k)
                bars.append({"label": self.tr(k, env), "count": v, "shown": fmt(v),
                             "color": color_of(self.eng.match(mt.text, k) if mt else None, i)})
            total = sum(amount(b) for b in boxes)
            return {**base, "type": "chart", "bars": bars, "total": total, "total_shown": fmt(total), "title": self.tr(name, env)}
        if kind == "calendar":
            df = next((k for k, f in fields.items() if f.type in ("monthday", "date")), None)
            now = self.eng.clock()
            items = []
            for b in boxes:
                try:
                    t = parse_time(b.values.get(df, ""), now.year)
                except (ValueError, AttributeError):
                    continue
                r = self.row(b, look, env, name)
                items.append({"id": b.id, "date": t.strftime("%Y-%m-%d"), "time": t.strftime("%H:%M"),
                              "title": r.get("title"), "color": (r.get("mark") or {}).get("color", AUTO[0]), "cardTap": r["cardTap"]})
            return {**base, "type": "calendar", "items": items, "today": now.strftime("%Y-%m-%d")}
        if kind == "table":
            cols = [k for k, f in fields.items() if f.type in ("text", "monthday", "date") or f.states]
            return {**base, "type": "table", "columns": [{"key": c, "label": self.tr(c, env)} for c in cols],
                    "rows": [self.row(b, look, env, name) for b in boxes]}
        rows = [self.row(b, look, env, name) for b in boxes]
        out = {**base, "type": "items", "rows": rows, "empty": self.empty_text(look, env), "heading": None, "search": None, "groups": None, "take": None,
               "more": self.tr("more", env)}
        if look is not None:
            h = look.child("heading")
            if h is not None:
                out["heading"] = self.tr(h.text.strip().strip('"'), env)
            sr = look.child("search")
            if sr is not None:
                out["search"] = {"fields": [x.strip() for x in sr.text.split(",")], "placeholder": self.tr("search", env)}
            tk = look.child("take")
            if tk is not None and tk.text.strip().isdigit():
                out["take"] = int(tk.text.strip())          # 最初に見せる件数。残りは「もっと見る」
            g = look.child("group")
            if g is not None and g.text.startswith("by "):
                gf = g.text[3:].strip()
                f = fields.get(gf)
                order = f.states if f is not None and f.states else sorted({str(b.values.get(gf, "")) for b in boxes})
                groups = []
                for i, st in enumerate(order):
                    ids = [r["id"] for r, b in zip(rows, boxes) if str(b.values.get(gf, "")) == st]
                    if not ids:
                        continue
                    mt = self.eng.match_for(thing, gf) if f is not None and f.states else None
                    groups.append({"value": st, "label": self.tr(st, env), "ids": ids,
                                   "color": color_of(self.eng.match(mt.text, st) if mt else None, i),
                                   "icon": self.icon_for(f"{thing}.{gf}", st)})
                out["groups"] = groups
        return out

    def empty_text(self, look: Node | None, env: Env) -> dict:
        e = look.child("empty") if look is not None else None
        if e is None:
            return {"text": self.tr("none", env), "button": None}
        toks = re.findall(r'"[^"]*"|\S+', e.text)
        text = toks[0].strip('"') if toks else ""
        btn = None
        if "button" in toks:
            pb = parse_button(" ".join(toks[toks.index("button") + 1:]))
            btn = self.button(pb, env, main=True, on=env.scene) if pb and self.can_open(pb["id"], env.scene) else None
        return {"text": self.tr(text, env), "button": btn}

    def detail_block(self, env: Env) -> dict:
        box = env.this
        look = self.looks.get(box.thing) or (self.looks.get(env.origin) if env.origin else None)
        r = self.row(box, look, env, env.origin or box.thing)
        fields = [{"label": self.tr(k, env), "value": self.show_value(box, k, env)} for k, f in self.eng.fields[box.thing].items()]
        return {"type": "detail", "title": r.get("title"), "sub": r.get("sub"), "mark": r.get("mark"), "lead": r.get("lead"),
                "fields": fields, "buttons": r["buttons"], "id": box.id, "on": env.origin or box.thing}

    def part_block(self, part: Node, value, env: Env) -> dict:
        body = self.part_bodies[part.name]
        in_ = part.child("in")
        inputs = {"__now__": self.eng.clock()}
        if in_ is not None:
            inputs[in_.text.split()[0]] = value
        try:
            vals = body.values(inputs) if body.steps else inputs
        except BodyError as e:
            return {"type": "part", "name": part.name, "lines": [f"（{e.message}）"], "mark": None}
        lines, mark = [], None
        for c in part.children:
            m = re.match(r'^text (?:"(.*)"|(\S+))$', c.text.strip())
            if c.keyword == "show" and m:
                m = type("M", (), {"group": lambda self, i, _m=m: _m.group(1) if _m.group(1) is not None else _m.group(2)})()
                t = self.tr(m.group(1), env)
                for _ in range(3):      # 値の中の {名前} も埋める
                    t2 = re.sub(r"\{(\w+)\}", lambda mm: self.tr(str(vals.get(mm.group(1), mm.group(0))), env)
                                if isinstance(vals.get(mm.group(1)), str) else str(vals.get(mm.group(1), mm.group(0))), t)
                    if t2 == t:
                        break
                    t = t2
                lines.append(t)
            elif c.keyword == "mark":
                st = c.text.strip()
                v = vals.get(st)
                mt = self.eng.matches.get(f"{part.name}.{st} to color")
                decl = next((x for x in part.walk() if x.keyword == st and x.text.startswith("[")), None)
                opts = states_of(decl.text) if decl else []
                idx = opts.index(v) if v in opts else 0
                mark = {"label": self.tr(v, env), "value": v, "color": color_of(self.eng.match(mt.text, v) if mt else None, idx)}
        return {"type": "part", "name": part.name, "lines": lines, "mark": mark}

    def input_block(self, name: str, env: Env) -> dict:
        """input。前の画面から with this で開いたら、その1件の編集になる（QUESTIONS_v0.2 U6）"""
        inp = self.inputs[name]
        thing = self.eng.input_thing(name)
        editing = env.this is not None and env.this.thing == thing
        fields = []
        for c in inp.children:
            f = self.eng.fields[thing][c.keyword]
            kind = {"monthday": "datetime-local", "date": "datetime-local", "number": "number", "count": "number"}.get(f.type, "text")
            if c.keyword == "memo" or "long" in c.text:
                kind = "textarea"
            value = ""
            if editing:
                value = str(env.this.values.get(c.keyword, ""))
                if kind == "datetime-local" and value:
                    try:
                        t = parse_time(value, self.eng.clock().year)
                        value = t.strftime("%Y-%m-%dT%H:%M")
                    except ValueError:
                        value = ""
            row = {"name": c.keyword, "label": self.tr(c.keyword, env), "kind": kind, "required": "required" in c.text, "value": value}
            if f.states:                                   # 状態は選ぶ（書いた状態のどれか）
                row["kind"] = "select"
                row["options"] = [{"value": st, "label": self.tr(st, env)} for st in f.states]
                row["value"] = value or f.states[0]
            fields.append(row)
        return {"type": "input", "name": name, "title": self.tr(name, env), "fields": fields, "this": env.this.id if editing else None,
                "submit": self.tr("save", env), "cancel": self.tr("cancel", env)}

    # ------------------------------------------------------------------
    def css(self) -> str:
        out = []
        for st in self.spec.decls("style"):
            words = st.text.split()
            name = words[0]
            media = words[2] if len(words) >= 3 and words[1] == "on" else None
            rules = []
            if name == "theme":
                for c in st.children:
                    w = c.raw.split()
                    if w[0] == "color" and len(w) == 3:
                        rules.append(f":root{{--{w[1]}:{color_of(w[2])}}}")
                    elif w[0] == "radius" and len(w) == 2:
                        rules.append(f":root{{--radius:{w[1]}px}}")
                    elif w[0] == "font" and len(w) >= 2:
                        rules.append(f":root{{--font:{' '.join(w[1:])}}}")
                out.append("\n".join(rules))
                continue
            scope = f".scene-{name}" if name in self.scenes else f".look-{name}"
            for c in st.children:
                sel = {"card": ".card", "title": ".title", "sub": ".sub", "mark": ".badge", "button": ".btn"}.get(c.keyword)
                if c.keyword == "gap":
                    rules.append(f"{scope} .rows{{gap:{c.text.strip()}px}}")
                elif c.keyword == "main" and name in self.scenes:
                    t = c.text.strip()
                    cols = "1fr" if t == "column" else f"repeat({t.split()[-1]},minmax(0,1fr))" if t.startswith("grid") else None
                    if cols:
                        rules.append(f"{scope} .slot-main .rows{{grid-template-columns:{cols}}}")
                elif c.keyword == "enter":
                    m = re.match(r"^(fade|slide|pop)\s+(\d+)ms$", c.text.strip())
                    if m:
                        rules.append(f"{scope} .enter{{animation:{m.group(1)} {m.group(2)}ms ease-out both}}")
                elif c.keyword == "reorder":
                    m = re.match(r"^slide\s+(\d+)ms$", c.text.strip())
                    if m:
                        rules.append(f"{scope}{{--reorder:{m.group(1)}ms}}")
                elif sel:
                    decl = self.css_decl(c.text)
                    if decl:
                        rules.append(f"{scope} {sel}{{{decl}}}")
            body = "\n".join(rules)
            if media:
                q = {"phone": "(max-width:599px)", "tablet": "(min-width:600px) and (max-width:1023px)", "wide": "(min-width:1024px)"}.get(media)
                body = f"@media {q}{{{body}}}" if q else body
            out.append(body)
        return "\n".join(out)

    @staticmethod
    def css_decl(text: str) -> str:
        decl = []
        for part in [p.strip() for p in text.split(",")]:
            w = part.split()
            if not w:
                continue
            k, v = w[0], w[1:] if len(w) > 1 else []
            if k == "round" and v:
                decl.append(f"border-radius:{v[0]}px")
            elif k == "shadow":
                lvl = (v or ["soft"])[0]
                decl.append({"soft": "box-shadow:var(--shadow-1)", "strong": "box-shadow:var(--shadow-2)", "none": "box-shadow:none"}.get(lvl, ""))
            elif k == "pad" and v:
                decl.append(f"padding:{v[0]}px")
            elif k == "size" and v:
                decl.append(f"font-size:{v[0]}px")
            elif k == "bold":
                decl.append("font-weight:700")
            elif k == "color" and v:
                decl.append(f"color:{color_of(v[0])}")
            elif k == "background" and v:
                decl.append(f"background:{color_of(v[0])}")
            elif k == "border" and v:
                decl.append(f"border-color:{color_of(v[0])}")
        return ";".join(d for d in decl if d)

    def title(self) -> str:
        first = next(iter(self.words.values()), {})
        for p in self.parts.values():
            for c in p.children:
                m = re.match(r'^text (?:"(.*)"|(\S+))$', c.text.strip())
                if c.keyword == "show" and m:
                    t = m.group(1) if m.group(1) is not None else m.group(2)
                    return first.get(t, t)
        return self.home or "app"


PAGE = pkgutil.get_data(__package__, "page.html").decode("utf-8")   # .pyz の中からでも読める


_STR_KEYS = ("user", "button", "on", "id", "input", "this", "text", "to", "lang")


def read_request(raw: bytes) -> dict | None:
    """POST の中身。JSON の object で、名前の値は文字、values は「文字 → 文字」だけ受け付ける"""
    try:
        data = json.loads(raw or b"{}")
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    for k in _STR_KEYS:
        if k in data and data[k] is not None and not isinstance(data[k], str):
            return None
    for k in ("values", "year_answers"):
        v = data.get(k)
        if v is None:
            continue
        if not isinstance(v, dict) or not all(isinstance(x, str) and (y is None or isinstance(y, str)) for x, y in v.items()):
            return None
    return data


def make_handler(app: App):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def end_headers(self):
            # よそのページに埋め込ませない・型を当て推量させない・行き先に URL を渡さない
            self.send_header("x-frame-options", "DENY")
            self.send_header("x-content-type-options", "nosniff")
            self.send_header("referrer-policy", "same-origin")
            super().end_headers()

        def _send(self, body: bytes, ctype: str, code=200):
            self.send_response(code)
            self.send_header("content-type", ctype)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8", code)

        def _session(self):
            return app.auth.sessions.who(cookie_token(self.headers.get("cookie"))) if app.auth else None

        def _user(self, name):
            if app.auth:                           # ログインが有る時は、送られてきた名前は使わない（cookie の鍵だけ信じる）
                return app.eng.login(self._session())
            return app.eng.login(name or "me")

        def _redirect(self, to, cookie=None):
            self.send_response(303)
            self.send_header("location", to)
            if cookie is not None:
                self.send_header("set-cookie", cookie)
            self.send_header("content-length", "0")
            self.end_headers()

        def _cookie(self, token, max_age):
            secure = "; Secure" if self.headers.get("x-forwarded-proto") == "https" else ""
            return f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}{secure}"

        def _auth_get(self, path) -> bool:
            """ログインの画面。処理したら True"""
            if path in ("/login", "/signup"):
                if path == "/signup" and not app.auth.signup:
                    self._redirect("/login")
                else:
                    page = login_page(app.title(), signup=path == "/signup", allow_signup=app.auth.signup)
                    self._send(page.encode(), "text/html; charset=utf-8")
                return True
            if path == "/logout":
                app.auth.sessions.end(cookie_token(self.headers.get("cookie")))
                self._redirect("/login", self._cookie("", 0))
                return True
            if self._session() is None:
                if path == "/":
                    self._redirect("/login")
                else:
                    self._json({"error": "ログインしてください", "login": True}, 401)
                return True
            return False

        def _auth_post(self, path, raw: bytes) -> bool:
            if path not in ("/login", "/signup"):
                if self._session() is None:
                    self._json({"error": "ログインしてください", "login": True}, 401)
                    return True
                if not (self.headers.get("content-type") or "").startswith("application/json"):
                    self._json({"error": "json で送ってください"}, 415)     # よそのページのフォームから押させない
                    return True
                return False
            f = {k: v[0] for k, v in parse_qs(raw.decode("utf-8", "replace")).items()}
            name, pw = f.get("name", "").strip(), f.get("password", "")
            ip = self.client_address[0]
            signup = path == "/signup"
            if not app.auth.allow(ip):
                err = "何度も間違えたので、少し待ってからやり直してください"
            elif signup and not app.auth.signup:
                err = "登録は閉じています"
            elif signup:
                if app.auth.users.exists(name):
                    err = "その名前はもう使われています"
                else:
                    try:
                        app.auth.users.add(name, pw)
                        err = ""
                    except ValueError as e:
                        err = str(e)
            else:
                err = "" if app.auth.users.verify(name, pw) else "名前か合言葉が違います"
            if err:
                app.auth.fail(ip)
                page = login_page(app.title(), err, signup=signup, allow_signup=app.auth.signup)
                self._send(page.encode(), "text/html; charset=utf-8", 401)
            else:
                self._redirect("/", self._cookie(app.auth.sessions.start(name), SESSION_SECONDS))
            return True

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if app.auth and u.path != "/favicon.ico" and self._auth_get(u.path):
                return
            if u.path == "/":
                lang = q.get("lang") or ("ja" if "ja" in app.words or not app.words else next(iter(app.words)))
                if not re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z]{2})?", lang):      # URL から来るので、言語の名前の形だけ通す
                    lang = "ja"
                acct = ""
                if app.auth:
                    acct = f'<div class="acct">{_html.escape(self._session() or "")} ・ <a href="/logout">ログアウト</a></div>'
                page = (PAGE.replace("<!--__ACCOUNT__-->", acct).replace('"__TITLE__"', json.dumps(app.title(), ensure_ascii=False).replace("</", "<\\/"))
                        .replace("__TITLE__", _html.escape(app.title())).replace("__HOME__", app.home or "")
                        .replace("__LANG__", lang).replace("/*__CSS__*/", app.css()))
                self._send(page.encode(), "text/html; charset=utf-8")
            elif u.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
            elif u.path == "/api/view":
                user = self._user(q.get("user"))
                try:
                    state = json.loads(q.get("state") or "{}")
                except ValueError:
                    state = None
                if not isinstance(state, dict):
                    self._json({"error": "state が読めません", "slots": [], "states": {}}, 400)
                    return
                if (q.get("scene") or app.home) not in app.scenes and (q.get("scene") or app.home) not in app.inputs:
                    self._json({"error": f"画面がありません: {q.get('scene')}", "slots": [], "states": {}}, 404)
                    return
                try:
                    v = app.view(q.get("scene") or app.home, user, state,
                                 q.get("this"), q.get("origin"), q.get("lang") or "ja")
                except Exception as e:    # 見せる途中で壊れても、理由を画面に出す
                    self._json({"error": f"{type(e).__name__}: {e}", "slots": [], "states": {}}, 500)
                    return
                v["notifications"] = [n for n in app.eng.notifications if n["user"] in (None, user.name)]
                self._json(v)
            elif u.path == "/api/events":
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.send_header("cache-control", "no-cache")
                self.end_headers()
                ev = threading.Event()
                eng, version = app.eng, app.version
                eng.listeners.append(ev.set)
                try:
                    while True:
                        if ev.wait(15):
                            ev.clear()
                            if app.version != version:          # spec が書き直された → 画面ごと読み直す
                                self.wfile.write(b"data: reload\n\n")
                                self.wfile.flush()
                                break
                            self.wfile.write(b"data: changed\n\n")
                        else:
                            self.wfile.write(b": keep\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    eng.listeners.remove(ev.set)
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            n = int(self.headers.get("content-length") or 0)
            raw = self.rfile.read(n)
            if app.auth and self._auth_post(self.path, raw):
                return
            data = read_request(raw)
            if data is None:
                self._json({"error": "リクエストが読めません"}, 400)
                return
            user = self._user(data.get("user"))
            try:
                if self.path == "/api/tap":
                    box = next((t[data["id"]] for t in app.eng.boxes.values() if data.get("id") in t), None) if data.get("id") else None
                    before = box.last_move if box is not None else None
                    mark, count = len(app.eng.trace), sum(len(t) for t in app.eng.boxes.values())
                    ctx = app.eng.tap(user, data["button"], data["on"], data.get("id"))
                    moves = [t for t in app.eng.trace[mark:] if t[0] == "move"]
                    # 取り消せるのは、押した1件が1回動いただけの時。他の箱も動いた・作った・消した時は、半分だけ戻ると食い違うので出さない
                    moved = (box is not None and box.last_move is not None and box.last_move is not before
                             and len(moves) == 1 and sum(len(t) for t in app.eng.boxes.values()) == count)
                    self._json({"nav": ctx.nav, "this": ctx.this.id if ctx.this is not None else None,
                                "undo": box.id if moved else None, "undo_label": app.tr("undo", Env(user, "", {}, None, None, data.get("lang") or "ja"))})
                elif self.path == "/api/undo":
                    box = next((t[data["id"]] for t in app.eng.boxes.values() if data["id"] in t), None)
                    if box is None:
                        raise RuleError("見つかりません")
                    app.eng.undo(box, user)
                    self._json({"ok": True})
                elif self.path == "/api/drag":
                    box = next((t[data["id"]] for t in app.eng.boxes.values() if data["id"] in t), None)
                    fld = app.state_field(box.thing) if box else None
                    env = Env(user, "", {}, None, None, data.get("lang") or "ja")
                    before = box.values.get(fld) if box else None
                    try:
                        app.eng.drag(user, data["id"], data["to"])
                    except RuleError as e:
                        if box is not None and "動けません" in str(e):   # 人が読める言い方にする
                            raise RuleError(f"「{app.tr(before, env)}」から「{app.tr(data['to'], env)}」へは動かせません（flow にない流れです）")
                        raise
                    self._json({"ok": True})
                elif self.path == "/api/submit":
                    thing = app.eng.input_thing(data["input"])
                    values = {}
                    for k, v in data.get("values", {}).items():
                        if v in ("", None):
                            continue
                        fl = app.eng.fields[thing].get(k)
                        if fl is not None and fl.states and v not in fl.states:
                            raise ValueError(f"{k} は {' / '.join(fl.states)} のどれかです")
                        if fl is not None and fl.states and (thing, k) in app.eng.flows:
                            raise ValueError(f"{k} は flow の通りに動く状態なので、入力では選べません（ボタンの rule で move する）")
                        if app.eng.fields[thing][k].type in ("monthday", "date"):
                            m = re.match(r"^\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})$", v)
                            if m:   # 日付の部品から来た形。monthday は年を持たない
                                v = f"{int(m.group(1))}/{int(m.group(2))} {int(m.group(3))}:{m.group(4)}"
                            parse_time(v, 2000)
                        values[k] = v
                    for c in app.inputs[data["input"]].children:       # input の決まり（required / from now）はサーバーでも守る
                        v = values.get(c.keyword)
                        if "required" in c.text and not v:
                            raise ValueError(f"{app.tr(c.keyword, Env(user, '', {}, None, None, data.get('lang') or 'ja'))} は必須です")
                        if "from now" in c.text and v and parse_time(v, app.eng.clock().year) < app.eng.clock():
                            raise ValueError(f"{c.keyword} は今より後にしてください（from now）")
                    now = app.eng.clock()
                    for k, v in list(values.items()):              # 年の無い月日が今日より前 → 来年かどうかを人に聞く（推測しない）
                        if app.eng.fields[thing][k].type == "monthday" and not re.match(r"^\d{4}", v):
                            t = parse_time(v, now.year)
                            if t.date() < now.date():
                                ans = (data.get("year_answers") or {}).get(k)
                                if ans is None:
                                    msg = app.tr("next-year", Env(user, "", {}, None, None, data.get("lang") or "ja")).replace("{year}", str(now.year + 1))
                                    self._json({"ask": {"field": k, "text": msg}})
                                    return
                                if ans == "next":
                                    values[k] = f"{now.year + 1}/{t.month}/{t.day} {t.hour}:{t.minute:02d}"
                    box = next((t[data["this"]] for t in app.eng.boxes.values() if data.get("this") in t), None) if data.get("this") else None
                    if box is not None:
                        app.eng.update(box, values, user)
                    else:
                        app.eng.submit(user, data["input"], values)
                    self._json({"ok": True, "edited": box is not None})
                elif self.path == "/api/says":
                    ctx = app.eng.says(user, data["text"])
                    self._json({"nav": ctx.nav})
                else:
                    self._json({"error": "not found"}, 404)
            except (RuleError, ValueError, KeyError) as e:
                self._json({"error": str(e).strip("'")}, 400)
            except (StopIteration, TypeError, AttributeError, IndexError, RecursionError) as e:   # 無い名前・変な形の値
                self._json({"error": f"リクエストが読めません（{type(e).__name__}）"}, 400)
    return H


class Auth:
    """ログインの持ち物。間違いが続く IP は少し止める"""
    def __init__(self, users: Users, signup: bool = False):
        self.users, self.signup, self.sessions = users, signup, Sessions()
        self.fails: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    def allow(self, ip: str) -> bool:
        with self.lock:
            recent = [t for t in self.fails.get(ip, []) if t > time.time() - 600]
            self.fails[ip] = recent
            return len(recent) < 10

    def fail(self, ip: str) -> None:
        with self.lock:
            self.fails.setdefault(ip, []).append(time.time())


def serve(spec: Spec, engine: Engine, port: int = 8000, host: str = "127.0.0.1", ticker: bool = True,
          auth: Auth | None = None):
    app = App(spec, engine)
    app.auth = auth
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.app = app
    httpd.daemon_threads = True
    if ticker:
        def loop():
            last = None
            while True:
                now = app.eng.clock().replace(second=0, microsecond=0)
                if now != last:
                    last = now
                    app.eng.tick(now)
                time.sleep(5)
        threading.Thread(target=loop, daemon=True).start()
    return httpd
