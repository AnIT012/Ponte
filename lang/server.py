"""画面を動かす（仕様 v0.2 6章）。Python 標準の http.server と、素の HTML / CSS / JavaScript だけ。

  python -m lang run spec/hub_app.lang --port 8000

- scene / look / part / input / style を読んで、画面の中身を JSON にして渡す。描くのはブラウザ。
- 箱が変わったら、開いている画面へ「変わった」を送る（Server-Sent Events）。画面は自動で最新になる。
- 時間の出来事は裏で1分ごとに見る。
"""
from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .parser import Node, Spec, match_arms
from .runtime import Ctx, Engine, RuleError
from .values import parse_time

COLORS = {"red": "#E5484D", "gray": "#8B8D98", "blue": "#3E63DD", "green": "#30A46C",
          "orange": "#F76B15", "yellow": "#FFC53D", "purple": "#8E4EC6", "black": "#1C2024"}


class App:
    def __init__(self, spec: Spec, engine: Engine):
        self.spec = spec
        self.eng = engine
        self.scenes = {s.name: s for s in spec.decls("scene")}
        self.looks = {l.name: l for l in spec.decls("look")}
        self.parts = {p.name: p for p in spec.decls("part")}
        self.inputs = {i.name: i for i in spec.decls("input")}
        self.home = next(iter(self.scenes), None)

    # ------------------------------------------------------------------
    # 画面の中身
    # ------------------------------------------------------------------
    def view(self, scene: str, user) -> dict:
        ctx = Ctx(user)
        if scene in self.inputs:
            return {"scene": scene, "slots": [{"slot": "main", "blocks": [self.input_block(scene)]}]}
        s = self.scenes.get(scene)
        if s is None:
            return {"scene": scene, "slots": [], "error": f"{scene} という画面はありません"}
        slots = []
        for c in s.children:
            if c.text.startswith("["):      # 画面の状態の宣言（ブラウザ側で持つ）
                continue
            slots.append({"slot": c.keyword, "blocks": self.content(c.text, c, ctx, scene)})
        return {"scene": scene, "slots": slots}

    def content(self, text: str, node: Node, ctx: Ctx, scene: str) -> list[dict]:
        text = text.strip()
        m = re.match(r"^match (.+)$", text)
        if m:
            value = self.eval_value(m.group(1), ctx)
            chosen = None
            for lefts, right, _ in match_arms(node):
                if str(value) in lefts:
                    chosen = right
                    break
                if "else" in lefts:
                    chosen = chosen or right
            return self.content(chosen, node, ctx, scene) if chosen else []
        if text == "nothing" or not text:
            return []
        m = re.match(r"^button (\S+)(?: named (.+?))?(?:\s+(toggle|set) .+)?$", text)
        if m:
            return [{"type": "button", "id": m.group(1), "label": m.group(2) or m.group(1), "on": scene}]
        m = re.match(r"^(\w+) as (\w+)$", text)
        if m:
            return [self.items_block(m.group(1), m.group(2), ctx)]
        if text in self.parts:
            return self.part_blocks(self.parts[text])
        if text in self.looks:
            return [{"type": "text", "text": text}]
        return [{"type": "text", "text": text, "muted": True}]

    def eval_value(self, expr: str, ctx: Ctx):
        m = re.match(r"^count of (\w+)$", expr.strip())
        if m:
            return len(self.source(m.group(1), ctx))
        return expr

    def source(self, name: str, ctx: Ctx):
        if name in self.eng.lists:
            return self.eng.list_items(name, ctx)
        items = self.eng.all(name)
        if ctx.user is not None:
            items = [b for b in items if self.eng.can(ctx.user, "see", name, b)]
        return items

    def items_block(self, name: str, kind: str, ctx: Ctx) -> dict:
        boxes = self.source(name, ctx)
        look = self.looks.get(name)
        thing = boxes[0].thing if boxes else (self.eng.lists[name].child("of").text.strip() if name in self.eng.lists else name)
        while thing in self.eng.lists:
            thing = self.eng.lists[thing].child("of").text.strip()
        spec_fields = self.eng.fields.get(thing, {})
        rows = []
        for b in boxes:
            row = {"id": b.id, "buttons": [], "values": {}}
            if look is not None:
                for c in look.children:
                    if c.keyword in ("title", "sub"):
                        row[c.keyword] = self.field_text(b, c.text)
                    elif c.keyword == "mark":
                        mm = re.match(r"^(\w+) of (\w+)$", c.text)
                        if mm:
                            mt = self.eng.match_for(b.thing, mm.group(2))
                            value = b.values.get(mm.group(2), "")
                            color = self.eng.match(mt.name, value) if mt else ""
                            row["mark"] = {"label": value, "color": COLORS.get(color, color)}
                    elif c.keyword == "button":
                        mm = re.match(r"^(\S+)(?: named (.+))?$", c.text)
                        row["buttons"].append({"id": mm.group(1), "label": mm.group(2) or mm.group(1)})
            else:
                texts = [k for k, f in spec_fields.items() if f.type in ("text", "monthday", "date")]
                if texts:
                    row["title"] = str(b.values.get(texts[0], ""))
                    row["sub"] = " · ".join(str(b.values.get(k, "")) for k in texts[1:])
                states = [k for k, f in spec_fields.items() if f.states]
                if states:
                    v = b.values.get(states[0], "")
                    mt = self.eng.match_for(b.thing, states[0])
                    color = self.eng.match(mt.name, v) if mt else "gray"
                    row["mark"] = {"label": v, "color": COLORS.get(color, color)}
            for k, f in spec_fields.items():
                if f.type in ("text", "monthday", "date") or f.states:
                    row["values"][k] = b.values.get(k, "")
            rows.append(row)
        columns = [k for k, f in spec_fields.items() if f.type in ("text", "monthday", "date") or f.states]
        return {"type": "items", "kind": kind, "name": name, "rows": rows, "columns": columns}

    def field_text(self, box, expr: str) -> str:
        expr = expr.strip()
        m = re.match(r"^(\w+) of (\w+)$", expr)
        if m and m.group(1) in self.parts:
            return str(box.values.get(m.group(2), ""))
        return str(box.values.get(expr, expr))

    def part_blocks(self, part: Node) -> list[dict]:
        out = []
        for c in part.children:
            m = re.match(r'^text "(.*)"$', c.text)
            if c.keyword == "show" and m:
                out.append({"type": "text", "text": m.group(1), "role": part.name})
        return out

    def input_block(self, name: str) -> dict:
        inp = self.inputs[name]
        thing = self.eng.input_thing(name)
        fields = []
        for c in inp.children:
            f = self.eng.fields[thing][c.keyword]
            fields.append({"name": c.keyword, "type": f.type, "required": "required" in c.text,
                           "hint": "9/24 23:59" if f.type in ("monthday", "date") else ""})
        return {"type": "input", "name": name, "fields": fields}

    # ------------------------------------------------------------------
    # 見た目（style → CSS）
    # ------------------------------------------------------------------
    def css(self) -> str:
        out = []
        for st in self.spec.decls("style"):
            words = st.text.split()
            name = words[0]
            media = words[2] if len(words) >= 3 and words[1] == "on" else None
            if name == "theme":
                for c in st.children:
                    m = re.match(r"^(color|space)\s+(\w+)\s+(\S+)$", c.raw)
                    if m:
                        out.append(f":root{{--{m.group(1)}-{m.group(2)}:{m.group(3) if m.group(1) == 'color' else m.group(3) + 'px'}}}")
                continue
            rules = []
            for c in st.children:
                sel = {"card": ".row", "title": ".title", "sub": ".sub", "mark": ".mark", "button": "button",
                       "gap": None, "main": None}.get(c.keyword, f".{c.keyword}")
                decl = self.css_decl(c.text)
                if c.keyword == "gap":
                    rules.append(f".block-{name} .rows{{gap:{c.text.strip()}px}}")
                elif c.keyword == "main" and name in self.scenes:
                    cols = "1fr" if c.text.strip() == "column" else f"repeat({c.text.split()[-1]},minmax(0,1fr))" if c.text.startswith("grid") else "1fr"
                    rules.append(f".scene-{name} .slot-main .rows{{grid-template-columns:{cols}}}")
                elif sel and decl:
                    rules.append(f".block-{name} {sel}{{{decl}}}")
            body = "\n".join(rules)
            if media:
                q = {"phone": "(max-width:599px)", "tablet": "(min-width:600px) and (max-width:1023px)", "wide": "(min-width:1024px)"}[media]
                body = f"@media {q}{{{body}}}"
            out.append(body)
        return "\n".join(out)

    @staticmethod
    def css_decl(text: str) -> str:
        decl = []
        for part in [p.strip() for p in text.split(",")]:
            w = part.split()
            if not w:
                continue
            if w[0] == "round" and len(w) > 1:
                decl.append(f"border-radius:{w[1]}px")
            elif w[0] == "shadow":
                decl.append("box-shadow:0 1px 2px rgba(0,0,0,.06),0 4px 16px rgba(0,0,0,.08)" if (w[1:] or ["soft"])[0] == "soft" else "box-shadow:0 8px 32px rgba(0,0,0,.18)")
            elif w[0] == "pad" and len(w) > 1:
                decl.append(f"padding:{w[1]}px")
            elif w[0] == "size" and len(w) > 1:
                decl.append(f"font-size:{w[1]}px")
            elif w[0] == "bold":
                decl.append("font-weight:700")
            elif w[0] == "color" and len(w) > 1:
                decl.append(f"color:{COLORS.get(w[1], w[1])}")
            elif w[0] == "background" and len(w) > 1:
                decl.append(f"background:{COLORS.get(w[1], w[1])}")
        return ";".join(decl)


# ----------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------

PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#F7F8FA;--panel:#fff;--text:#1C2024;--muted:#6B7280;--line:#E5E7EB;--color-main:#3E63DD;--radius:12px}
@media (prefers-color-scheme:dark){:root{--bg:#111113;--panel:#1B1B1F;--text:#EDEEF0;--muted:#9CA3AF;--line:#2E2E33}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 system-ui,-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif}
.app{max-width:1080px;margin:0 auto;padding:16px;display:grid;gap:16px;grid-template-columns:1fr;grid-template-areas:"top" "main" "side" "bottom"}
@media (min-width:900px){.app.has-side{grid-template-columns:2fr 1fr;grid-template-areas:"top top" "main side" "bottom bottom"}}
.slot-top{grid-area:top}.slot-main{grid-area:main}.slot-side{grid-area:side}.slot-bottom{grid-area:bottom}
.rows{display:grid;gap:12px}.kind-cards .rows{grid-template-columns:repeat(auto-fill,minmax(240px,1fr))}
.row{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:14px;display:flex;flex-direction:column;gap:6px;transition:transform .15s}
.kind-list .row{display:grid;grid-template-columns:auto 1fr auto;align-items:center;column-gap:10px;padding:10px 14px}
.kind-list .row .title{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.kind-list .row .sub{grid-column:2}
.kind-list .row .btns{grid-row:1 / span 2;grid-column:3;display:flex;gap:6px}.kind-list .row button{white-space:nowrap}
.slot-head{font-size:13px;color:var(--muted);margin:0 0 8px}
.title{font-weight:600}.sub{color:var(--muted);font-size:13px}
.mark{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}.mark i{width:8px;height:8px;border-radius:50%;display:inline-block}
button{font:inherit;border:0;border-radius:8px;padding:8px 14px;background:var(--color-main);color:#fff;cursor:pointer}
button:hover{filter:brightness(1.08)}.row button{padding:6px 12px;font-size:13px}.btns{display:flex;gap:6px}
.text{color:var(--muted)}.role-Header{font-size:22px;font-weight:700;color:var(--text)}
table{width:100%;border-collapse:collapse;background:var(--panel);border-radius:var(--radius);overflow:hidden}td,th{padding:8px 12px;border-bottom:1px solid var(--line);text-align:left}
form{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:20px;display:grid;gap:14px;max-width:480px}
label{display:grid;gap:4px;font-size:13px;color:var(--muted)}input{font:inherit;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--text)}
.toast{position:fixed;right:16px;bottom:16px;display:grid;gap:8px;max-width:360px}.toast div{background:var(--text);color:var(--bg);padding:10px 14px;border-radius:10px;font-size:13px;box-shadow:0 8px 24px rgba(0,0,0,.2)}
.err{color:#E5484D;font-size:13px}.nav{display:flex;gap:8px;margin-bottom:4px}.nav a{color:var(--muted);font-size:13px;cursor:pointer}
__CSS__
</style></head><body>
<div id="root"></div><div class="toast" id="toast"></div>
<script>
const USER = new URLSearchParams(location.search).get("user") || "me";
let scene = "__HOME__", seen = 0;
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
async function post(path, body){ const r = await fetch(path,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({user:USER,...body})}); return r.json(); }
function renderBlock(b){
  if(b.type==="text") return `<div class="text ${b.role?"role-"+b.role:""}">${esc(b.text)}</div>`;
  if(b.type==="button") return `<button data-tap="${esc(b.id)}" data-on="${esc(b.on)}">${esc(b.label)}</button>`;
  if(b.type==="input") return `<form data-input="${esc(b.name)}">${b.fields.map(f=>`<label>${esc(f.name)}${f.required?" *":""}<input name="${esc(f.name)}" placeholder="${esc(f.hint)}" ${f.required?"required":""}></label>`).join("")}<div class="err" id="err"></div><button type="submit">送る</button><a onclick="go('__HOME__')">戻る</a></form>`;
  if(b.type==="items"){
    if(b.kind==="table") return `<div class="block-${b.name} kind-table"><table><tr>${b.columns.map(c=>`<th>${esc(c)}</th>`).join("")}</tr>${b.rows.map(r=>`<tr>${b.columns.map(c=>`<td>${esc(r.values[c])}</td>`).join("")}</tr>`).join("")}</table></div>`;
    return `<div class="block-${b.name} kind-${b.kind}"><div class="rows">${b.rows.map(r=>`<div class="row">
      ${r.mark?`<span class="mark"><i style="background:${esc(r.mark.color)}"></i>${esc(r.mark.label)}</span>`:""}
      <div class="title">${esc(r.title)}</div>${r.sub?`<div class="sub">${esc(r.sub)}</div>`:""}
      <div class="btns">${r.buttons.map(x=>`<button data-tap="${esc(x.id)}" data-on="${esc(b.name)}" data-id="${esc(r.id)}">${esc(x.label)}</button>`).join("")}</div>
    </div>`).join("")}</div></div>`;
  }
  return "";
}
async function render(){
  const v = await (await fetch(`/api/view?scene=${encodeURIComponent(scene)}&user=${encodeURIComponent(USER)}`)).json();
  const hasSide = v.slots.some(s=>s.slot==="side" && s.blocks.length);
  document.getElementById("root").innerHTML = `<div class="app scene-${esc(v.scene)} ${hasSide?"has-side":""}">${v.slots.map(s=>`<section class="slot-${s.slot}">${s.blocks.map(renderBlock).join("")}</section>`).join("")}</div>`;
  const n = v.notifications || [];
  const fresh = n.slice(seen); seen = n.length;
  const t = document.getElementById("toast");
  fresh.slice(-3).forEach(x=>{ const d=document.createElement("div"); d.textContent=`${x.rule}: ${x.text}`; t.appendChild(d); setTimeout(()=>d.remove(),5000); });
}
function go(s){ scene = s; render(); }
document.addEventListener("click", async e=>{
  const b = e.target.closest("[data-tap]"); if(!b) return;
  const r = await post("/api/tap",{button:b.dataset.tap,on:b.dataset.on,id:b.dataset.id||null});
  if(r.nav) go(r.nav); else render();
});
document.addEventListener("submit", async e=>{
  e.preventDefault(); const f = e.target;
  const values = Object.fromEntries(new FormData(f).entries());
  for(const k in values) if(values[k]==="") delete values[k];
  const r = await post("/api/submit",{input:f.dataset.input,values});
  if(r.error){ document.getElementById("err").textContent = r.error; return; }
  go("__HOME__");
});
new EventSource("/api/events").onmessage = () => render();
render();
</script></body></html>"""


def make_handler(app: App):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _user(self, name):
            return app.eng.login(name or "me")

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path == "/":
                title = app.home or "app"
                page = PAGE.replace("__TITLE__", title).replace("__HOME__", app.home or "").replace("__CSS__", app.css())
                body = page.encode()
                self.send_response(200)
                self.send_header("content-type", "text/html; charset=utf-8")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif u.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
            elif u.path == "/api/view":
                user = self._user(q.get("user"))
                v = app.view(q.get("scene") or app.home, user)
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
                    self._json({"nav": ctx.nav})
                elif self.path == "/api/submit":
                    thing = app.eng.input_thing(data["input"])
                    values = data.get("values", {})
                    for k, v in values.items():
                        if app.eng.fields[thing][k].type in ("monthday", "date"):
                            parse_time(v, 2000)   # 形だけ確かめる
                    app.eng.submit(user, data["input"], values)
                    self._json({"ok": True})
                elif self.path == "/api/says":
                    ctx = app.eng.says(user, data["text"])
                    self._json({"nav": ctx.nav})
                else:
                    self._json({"error": "not found"}, 404)
            except (RuleError, ValueError, KeyError) as e:
                self._json({"error": str(e)}, 400)
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
