"""`ponte doc`: 仕様を、コードを読まない人にも読める1枚の HTML にする。

人が決めたこと（データ・流れ・誰が何をできるか・ルールとその理由・AIに任せた所と約束）と、
まだ決めていないこと・確かめていない所を並べる。書いた人以外が仕様を確かめるためのもの。
"""
from __future__ import annotations

import html
import re

from .checker import actions, check, rules, things
from .examples import holes, run_examples
from .parser import Spec, flow_parts, parse_button, relate_lines, thing_fields

VERBS = {"see": "見る", "change": "変える", "create": "作る", "remove": "消す", "move": "動かす"}
RELS = {"then": "{a} の後に {b} が動く", "then no": "{a} の後は {b} が動かない", "before": "{a} が {b} より先",
        ">": "{a} と {b} が同時なら {a} が勝つ", "else": "{a} がうまくいかなければ {b}"}


def _e(s) -> str:
    return html.escape(str(s))


def _words(spec: Spec) -> dict[str, str]:
    """画面の文字（words ja があれば日本語の名前で見せる）"""
    for w in spec.decls("words"):
        if w.name == "ja":
            return {c.keyword: c.text.strip() for c in w.children}
    return {}


def build(spec: Spec, title: str | None = None) -> str:
    words = _words(spec)
    name = lambda x: f"{_e(words[x])} <code>{_e(x)}</code>" if x in words else f"<code>{_e(x)}</code>"
    sections = []

    # データ
    rows = []
    for t in things(spec).values():
        items = []
        for f in thing_fields(t):
            kind = " / ".join(name(s) for s in f.states) if f.states else _e(f.type)
            gone = f"（{_e(f.name)} の先が消えたら: {_e(f.gone)}）" if f.gone else ""
            items.append(f"<li>{name(f.name)} … {kind}{gone}</li>")
        rows.append(f"<h3>{name(t.name)}</h3><ul>{''.join(items)}</ul>")
    sections.append(("data", "データの形", "".join(rows)))

    # 流れ
    flows = []
    for f in spec.decls("flow"):
        if f.name == "scene":
            continue
        try:
            edges, wins = flow_parts(f)
        except Exception:
            continue
        arrows = "".join(f"<li>{name(a)} → {name(b)}</li>" for a, b in edges)
        win = "".join(f"<li>同時なら {name(a)} が {name(b)} に勝つ</li>" for a, b in wins)
        flows.append(f"<h3><code>{_e(f.name)}</code></h3><ul>{arrows}{win}</ul><p class='note'>矢印のない動きはできません。</p>")
    if flows:
        sections.append(("flow", "状態の流れ", "".join(flows)))

    # 誰が何をできるか
    who = []
    for w in spec.decls("who"):
        for c in w.children:
            m = re.match(r"^(\w+)\s+can\s+(\w+)\s+(\w+)(?:\s+where\s+(.+))?$", c.raw.strip())
            if m:
                role, verb, t, cond = m.groups()
                who.append(f"<tr><td>{_e('みんな' if role == 'user' else role)}</td><td>{name(t)} を{_e(VERBS.get(verb, verb))}</td>"
                           f"<td>{_e(cond or '（いつでも）')}</td></tr>")
    sections.append(("who", "誰が何をできるか",
                     f"<p>ここにないことは、誰にもできません。</p><table><tr><th>誰が</th><th>できること</th><th>条件</th></tr>{''.join(who)}</table>"))

    # きまり
    rel = relate_lines(spec)
    rs = []
    for r in rules(spec).values():
        why = r.child("why")
        when = r.child("when")
        dos = [d.text.strip() for d in r.children_of("do")]
        wh = [w.text.strip() for w in r.children_of("where")]
        n_ex = len(r.children_of("example"))
        links = [_e(RELS.get(k, "{a} " + k + " {b}").format(a=a, b=b)) for a, k, b, _ in rel if r.name in (a, b)]
        rs.append(f"<div class='card'><h3>{_e(r.name)}</h3>"
                  + (f"<p class='why'>{_e(why.text.strip())}</p>" if why else "<p class='why missing'>（理由が書かれていません）</p>")
                  + "<dl>"
                  + (f"<dt>きっかけ</dt><dd><code>{_e(when.text.strip())}</code></dd>" if when else "")
                  + (f"<dt>条件</dt><dd>{'<br>'.join(f'<code>{_e(x)}</code>' for x in wh)}</dd>" if wh else "")
                  + f"<dt>やること</dt><dd>{'<br>'.join(f'<code>{_e(x)}</code>' for x in dos) or 'なし'}</dd>"
                  + (f"<dt>つながり</dt><dd>{'<br>'.join(links)}</dd>" if links else "")
                  + f"<dt>例</dt><dd>{n_ex}つ</dd></dl></div>")
    sections.append(("rules", "ルール", "".join(rs)))

    # AIに任せた所
    acts = []
    for a in actions(spec).values():
        by = a.child("by")
        ex = [c.text.strip() for c in a.children_of("example")]
        nv = [c.text.strip() for c in a.children_of("never")]
        el = a.child("else")
        acts.append(f"<div class='card'><h3>{_e(a.name)}</h3><dl>"
                    f"<dt>入るもの</dt><dd><code>{_e(a.child('in').text.strip() if a.child('in') else 'なし')}</code></dd>"
                    f"<dt>答えの形</dt><dd><code>{_e(a.child('out').text.strip() if a.child('out') else 'なし')}</code></dd>"
                    f"<dt>誰が中身を書くか</dt><dd>{_e(by.text.strip() if by else 'ai')}</dd>"
                    f"<dt>例（守ること）</dt><dd>{'<br>'.join(f'<code>{_e(x)}</code>' for x in ex)}</dd>"
                    + (f"<dt>してはいけないこと</dt><dd>{'<br>'.join(f'<code>{_e(x)}</code>' for x in nv)}</dd>" if nv else "")
                    + (f"<dt>答えが出ないとき</dt><dd><code>{_e(el.text.strip())}</code></dd>" if el else "")
                    + "</dl></div>")
    if acts:
        sections.append(("ai", "AI の担当部分と約束", "<p>AI が書いた中身は、下の例と「してはいけないこと」を使って機械的に確かめます。</p>" + "".join(acts)))

    # 画面
    def label(text: str) -> str:                   # ボタンは画面に出る名前で（無ければ名前そのもの）
        pb = parse_button(text.strip())
        if not pb:
            return f"<code>{_e(text.strip())}</code>"
        shown = words.get(pb["label"], pb["label"]) if pb["label"] else None
        return f"{_e(shown)} <code>{_e(pb['id'])}</code>" if shown else f"<code>{_e(pb['id'])}</code>"
    scr = []
    for sc in spec.decls("scene"):
        items = []
        for c in sc.children:
            if c.text.startswith("["):
                continue
            t = c.text.strip()
            if t.startswith("button "):
                items.append(f"<li>ボタン {label(t[7:])}</li>")
            else:
                items.append(f"<li><code>{_e(t)}</code></li>")
        scr.append(f"<h3>{name(sc.name)}</h3><ul>{''.join(items)}</ul>")
    for inp in spec.decls("input"):
        fs = []
        for c in inp.children:
            note = " （必須）" if "required" in c.text else ""
            note += " （今より後）" if "from now" in c.text else ""
            fs.append(f"<li>{name(c.keyword)}{_e(note)}</li>")
        scr.append(f"<h3>入力 {name(inp.name)}</h3><ul>{''.join(fs)}</ul>")
    btns = {}
    for lk in spec.decls("look"):
        for c in lk.children_of("button"):
            btns.setdefault(lk.name, []).append(label(c.text))
    if btns:
        scr.append("<h3>一覧のボタン</h3><ul>" + "".join(f"<li>{name(k)}: {' / '.join(v)}</li>" for k, v in btns.items()) + "</ul>")
    if scr:
        sections.append(("screens", "画面", "".join(scr)))

    # まだ決めていないこと・確かめていない所
    open_items = []
    for f in check(spec):
        if f.code in ("E05", "E06"):
            path, line = spec.where(f.line)
            open_items.append(f"<li>{_e(f.message)} <span class='where'>{_e(path)}:{line}</span></li>")
    todo = f"<h3>まだ決めていないこと（{len(open_items)}）</h3>" + (f"<ul>{''.join(open_items)}</ul>" if open_items else "<p>ありません。</p>")
    if [f for f in check(spec) if f.is_error]:
        todo += "<h3>例で確かめていない部分</h3><p class='missing'>check が通っていないため、まだ数えていません（<code>ponte check</code>）。</p>"
    else:
        hole_items = [f"<li>{_e(h.message)}</li>" for h in holes(spec, run_examples(spec))]
        todo += f"<h3>例で確かめていない部分（{len(hole_items)}）</h3>" + (f"<ul>{''.join(hole_items)}</ul>" if hole_items else "<p>ありません。</p>")
    sections.append(("open", "残っていること", todo))

    import os
    title = title or words.get("app-name") or (os.path.splitext(os.path.basename(spec.path))[0] if spec.path else "Ponte")
    nav = "".join(f'<a href="#{i}">{_e(t)}</a>' for i, t, _ in sections)
    body = "".join(f'<section id="{i}"><h2>{_e(t)}</h2>{inner}</section>' for i, t, inner in sections)
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)}：仕様のまとめ</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"%3E%3Cdefs%3E%3ClinearGradient id="pi" x1="0" x2="1"%3E%3Cstop offset=".15" stop-color="#FF7355"/%3E%3Cstop offset=".85" stop-color="#83C3FF"/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width="100" height="100" rx="24" fill="#1F2340"/%3E%3Cpath d="M24 62 C 38 28, 62 28, 76 62" stroke="url%28#pi%29" stroke-width="9" fill="none" stroke-linecap="round"/%3E%3Ccircle cx="24" cy="62" r="13" fill="#FF7355"/%3E%3Ccircle cx="76" cy="62" r="13" fill="#83C3FF"/%3E%3C/svg%3E">
<style>
:root{{--bg:#f7f7f5;--fg:#1f2328;--sub:#6b7280;--card:#fff;--line:#e5e7eb;--accent:#2f6fd6;--warn:#b42318}}
@media (prefers-color-scheme: dark){{:root{{--bg:#16171a;--fg:#e6e6e6;--sub:#9aa0a6;--card:#202226;--line:#2f3237;--accent:#83c3ff;--warn:#ff8a80}}}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.8 system-ui,sans-serif;padding:0 16px 60px}}
.wrap{{max-width:860px;margin:0 auto}} header{{padding:28px 0 8px}} h1{{margin:0;font-size:28px}} .lead{{color:var(--sub);margin:6px 0 0}}
nav{{display:flex;flex-wrap:wrap;gap:14px;padding:12px 0;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg)}}
nav a{{color:var(--accent);text-decoration:none;font-size:14px}}
h2{{margin:36px 0 12px;font-size:22px}} h3{{margin:18px 0 6px;font-size:17px}}
code{{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.88em;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:1px 6px;overflow-wrap:anywhere}}
table{{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;font-size:14.5px}}
th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}} th{{color:var(--sub);font-weight:600}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:10px 0}}
.card h3{{margin-top:0}} dl{{display:grid;grid-template-columns:10.5em 1fr;gap:4px 12px;margin:6px 0 0;font-size:14.5px}} dt{{color:var(--sub)}} dd{{margin:0}}
.why{{margin:0 0 4px}} .missing{{color:var(--warn)}} .note{{color:var(--sub);font-size:14px;margin:4px 0}} .where{{color:var(--sub);font-size:13px}}
@media (max-width:560px){{dl{{grid-template-columns:1fr}} dt{{margin-top:6px}}}}
</style></head><body><div class="wrap">
<header><h1>{_e(title)}</h1><p class="lead">この仕様で決まっていることの一覧です（<code>ponte doc</code> で生成）。</p></header>
<nav>{nav}</nav>
{body}
</div></body></html>
"""
