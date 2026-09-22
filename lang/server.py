"""画面を動かす（仕様 v0.2 6章）。Python 標準の http.server と、素の HTML / CSS / JavaScript だけ。

  python -m lang run spec/hub_app.lang --port 8000

サーバーは scene / look / part / input / style / words を読んで「何を見せるか」を JSON にする。
描くのはブラウザ。画面の状態（タブ・メニューの開閉）はブラウザが持ち、見せる時にサーバーへ渡す。
箱が変わると開いている画面へ「変わった」を送る（Server-Sent Events）。
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .body import Body, BodyError
from .parser import Node, Spec, match_arms, states_of
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
        self.scenes = {s.name: s for s in spec.decls("scene")}
        self.looks = {l.name: l for l in spec.decls("look")}
        self.parts = {p.name: p for p in spec.decls("part")}
        self.inputs = {i.name: i for i in spec.decls("input")}
        self.words = {w.name: {c.keyword: c.text.strip().strip('"') for c in w.children} for w in spec.decls("words")}
        self.home = next(iter(self.scenes), None)
        self.part_bodies = {}
        for name, p in self.parts.items():
            lines = [c for c in p.children if re.match(r"^\w+\s*(\[[^\]]*\])?\s*=", c.raw)]
            in_ = p.child("in")
            self.part_bodies[name] = Body(p, {}, [in_.text.split()[0]] if in_ else [], {}, single_result=False, lines=lines)
        self.tones = {}
        for st in spec.decls("style"):
            for c in st.children:
                m = re.search(r"\btone\s+(\w+)", c.text)
                if m:
                    self.tones[c.keyword] = m.group(1)

    # ------------------------------------------------------------------
    def tr(self, key, env: Env) -> str:
        key = "" if key is None else str(key)
        return self.words.get(env.lang, {}).get(key, key)

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
        if scene in self.inputs:
            top = []
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
                     "options": [{"value": v, "label": self.tr(v, env)} for v in vals]}]
        m = re.match(r"^button\s+(\S+)(?:\s+named\s+(.+?))?(?:\s+(toggle|set)\s+(\w+)(?:\s+(\w+))?)?$", text)
        if m:   # 画面の下のボタンだけ目立たせる。上のボタンは控えめ
            return [self.button(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), env, main=(node.keyword == "bottom"), on=env.scene)]
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
    def button(self, bid, label, action, state, value, env: Env, main: bool, on: str) -> dict:
        tone = self.tones.get(bid) or ("main" if main else "quiet")
        b = {"type": "button", "id": bid, "label": self.tr(label or bid, env), "tone": tone, "on": on}
        if action == "toggle":
            b["act"] = {"kind": "toggle", "state": state}
        elif action == "set":
            b["act"] = {"kind": "set", "state": state, "value": value}
        return b

    def can_press(self, box: Box, bid: str, on: str) -> bool:
        """このボタンの rule が `move this to X` なら、flow でいま X へ動けるかを見る（動けないボタンは押せなくする）"""
        for r in self.eng.rules.values():
            w = r.child("when")
            if w is None or not re.match(rf"^user taps {re.escape(bid)} on ({re.escape(on)}|{re.escape(box.thing)})$", w.text.strip()):
                continue
            for d in r.children_of("do"):
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
        return {"label": self.tr(v, env), "value": v, "color": color_of(self.eng.match(mt.name, v) if mt else None, idx)}

    def show_value(self, box: Box, fld: str, env: Env):
        f = self.eng.fields[box.thing].get(fld)
        v = box.values.get(fld, "")
        if f is not None and f.type in self.eng.fields and v:
            ub = self.eng.boxes.get(f.type, {}).get(v)
            return ub.values.get("name", v) if ub else v
        return self.tr(v, env) if f is not None and f.states else v

    def has_card_rule(self, name: str) -> bool:
        thing = self.thing_of(name)
        for r in self.eng.rules.values():
            w = r.child("when")
            if w is not None and re.match(rf"^user taps card on ({re.escape(name)}|{re.escape(thing)})$", w.text.strip()):
                return True
        return False

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
                elif c.keyword == "button":
                    m = re.match(r"^(\S+)(?:\s+named\s+(.+?))?(?:\s+(toggle|set)\s+(\w+)(?:\s+(\w+))?)?$", c.text.strip())
                    b = self.button(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), env, main=(nb == 0), on=list_name)
                    if not b.get("act") and not self.can_press(box, m.group(1), list_name):
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
                cols.append({"state": st, "label": self.tr(st, env), "color": color_of(self.eng.match(mt.name, st) if mt else None, i),
                             "rows": [self.row(b, look, env, name) for b in boxes if b.values.get(sf) == st]})
            return {**base, "type": "board", "columns": cols, "draggable": (thing, sf) in self.eng.flows}
        if kind == "chart":
            states = fields[sf].states if sf else []
            mt = self.eng.match_for(thing, sf) if sf else None
            bars = [{"label": self.tr(st, env), "count": sum(1 for b in boxes if b.values.get(sf) == st),
                     "color": color_of(self.eng.match(mt.name, st) if mt else None, i)} for i, st in enumerate(states)]
            return {**base, "type": "chart", "bars": bars, "total": len(boxes), "title": self.tr(name, env)}
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
        return {**base, "type": "items", "rows": [self.row(b, look, env, name) for b in boxes],
                "empty": self.empty_text(look, env)}

    def empty_text(self, look: Node | None, env: Env) -> str:
        if look is not None and look.child("empty") is not None:
            return self.tr(look.child("empty").text.strip().strip('"'), env)
        return self.tr("まだありません", env)

    def detail_block(self, env: Env) -> dict:
        box = env.this
        look = self.looks.get(box.thing) or (self.looks.get(env.origin) if env.origin else None)
        r = self.row(box, look, env, env.origin or box.thing)
        fields = [{"label": self.tr(k, env), "value": self.show_value(box, k, env)} for k, f in self.eng.fields[box.thing].items()]
        return {"type": "detail", "title": r.get("title"), "sub": r.get("sub"), "mark": r.get("mark"),
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
            m = re.match(r'^text "(.*)"$', c.text.strip())
            if c.keyword == "show" and m:
                t = self.tr(m.group(1), env)
                for _ in range(3):      # 値の中の {名前} も埋める
                    t2 = re.sub(r"\{(\w+)\}", lambda mm: str(vals.get(mm.group(1), mm.group(0))), t)
                    if t2 == t:
                        break
                    t = t2
                lines.append(t)
            elif c.keyword == "mark":
                st = c.text.strip()
                v = vals.get(st)
                mt = next((x for x in self.eng.matches.values() if x.text.split(" to ")[0].strip() == f"{part.name}.{st}"), None)
                decl = next((x for x in part.children if x.keyword == st and x.text.startswith("[")), None)
                opts = states_of(decl.text) if decl else []
                idx = opts.index(v) if v in opts else 0
                mark = {"label": self.tr(v, env), "value": v, "color": color_of(self.eng.match(mt.name, v) if mt else None, idx)}
        return {"type": "part", "name": part.name, "lines": lines, "mark": mark}

    def input_block(self, name: str, env: Env) -> dict:
        inp = self.inputs[name]
        thing = self.eng.input_thing(name)
        fields = []
        for c in inp.children:
            f = self.eng.fields[thing][c.keyword]
            kind = {"monthday": "datetime-local", "date": "datetime-local", "number": "number", "count": "number"}.get(f.type, "text")
            fields.append({"name": c.keyword, "label": self.tr(c.keyword, env), "kind": kind, "required": "required" in c.text})
        return {"type": "input", "name": name, "title": self.tr(name, env), "fields": fields,
                "submit": self.tr("保存", env), "cancel": self.tr("キャンセル", env)}

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
        for p in self.parts.values():
            for c in p.children:
                m = re.match(r'^text "(.*)"$', c.text.strip())
                if c.keyword == "show" and m:
                    return m.group(1)
        return self.home or "app"


PAGE = open(__file__.replace("server.py", "page.html"), encoding="utf-8").read()


def make_handler(app: App):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body: bytes, ctype: str, code=200):
            self.send_response(code)
            self.send_header("content-type", ctype)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8", code)

        def _user(self, name):
            return app.eng.login(name or "me")

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path == "/":
                lang = q.get("lang") or ("ja" if "ja" in app.words or not app.words else next(iter(app.words)))
                page = (PAGE.replace("__TITLE__", app.title()).replace("__HOME__", app.home or "")
                        .replace("__LANG__", lang).replace("/*__CSS__*/", app.css()))
                self._send(page.encode(), "text/html; charset=utf-8")
            elif u.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
            elif u.path == "/api/view":
                user = self._user(q.get("user"))
                try:
                    v = app.view(q.get("scene") or app.home, user, json.loads(q.get("state") or "{}"),
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
                app.eng.listeners.append(ev.set)
                try:
                    while True:
                        if ev.wait(15):
                            ev.clear()
                            self.wfile.write(b"data: changed\n\n")
                        else:
                            self.wfile.write(b": keep\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    app.eng.listeners.remove(ev.set)
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            n = int(self.headers.get("content-length") or 0)
            data = json.loads(self.rfile.read(n) or b"{}")
            user = self._user(data.get("user"))
            try:
                if self.path == "/api/tap":
                    ctx = app.eng.tap(user, data["button"], data["on"], data.get("id"))
                    self._json({"nav": ctx.nav, "this": ctx.this.id if ctx.this is not None else None})
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
                        if app.eng.fields[thing][k].type in ("monthday", "date"):
                            m = re.match(r"^\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})$", v)
                            if m:   # 日付の部品から来た形。monthday は年を持たない
                                v = f"{int(m.group(1))}/{int(m.group(2))} {int(m.group(3))}:{m.group(4)}"
                            parse_time(v, 2000)
                        values[k] = v
                    app.eng.submit(user, data["input"], values)
                    self._json({"ok": True})
                elif self.path == "/api/says":
                    ctx = app.eng.says(user, data["text"])
                    self._json({"nav": ctx.nav})
                else:
                    self._json({"error": "not found"}, 404)
            except (RuleError, ValueError, KeyError) as e:
                self._json({"error": str(e).strip("'")}, 400)
    return H


def serve(spec: Spec, engine: Engine, port: int = 8000, host: str = "127.0.0.1", ticker: bool = True):
    app = App(spec, engine)
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.daemon_threads = True
    if ticker:
        def loop():
            last = None
            while True:
                now = engine.clock().replace(second=0, microsecond=0)
                if now != last:
                    last = now
                    engine.tick(now)
                time.sleep(5)
        threading.Thread(target=loop, daemon=True).start()
    return httpd
