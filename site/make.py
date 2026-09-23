"""ホームページの中身を作る（手で書かない。docs と実装から作る）。

  python site/make.py && python site/build.py

  landing.html    … トップ（構文の見本 site/samples と page.body.html から）
  learn.src.html      … 入門（docs/入門.md から）
  reference.src.html  … 道具とエラー（ponte の TOOLS・forms・errors・std・コマンドの一覧から）

どれも head.html（フォントと色）+ page.css + header.html を共有する。
"""
import argparse
import html
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
from highlight import highlight, states_in  # noqa: E402
from md import inline, render  # noqa: E402

REPO = "https://github.com/AnIT012/nameless-lang"
DOC = REPO + "/blob/main/docs/"
BLOB = REPO + "/blob/main/"

SLIDES = [
    ("1", "データの形を書く", "thing には、アプリが持つデータの形を書きます。項目の名前と型を並べておけば、保存や読み書きは Ponte が引き受けます。状態は <code>[todo | done]</code> のように、取りうる値を全部書いておきます。"),
    ("2", "流れと、誰が何をできるか", "flow には状態がどう移れるかを、who には誰が何をしてよいかを書きます。who に書いていない操作は誰にもできないので、権限の書き忘れはエラーとして見つかります。"),
    ("3", "きっかけと、やること", "rule には、きっかけとやることを一組で書きます。when に書けるのは時刻やボタンのような出来事だけで、「明日まで」のような条件は list の where で絞ります。"),
    ("4", "例がそのままテストになる", "rule の下に example を書くと、それがテストになります。<code>ponte test</code> は例が通るかを確かめるだけでなく、まだ例で確かめていないルールや状態の変化も教えてくれます。"),
    ("5", "AIに任せる部分には約束を", "処理の中身をAIに書いてもらうときは、action に入力と答えの例、してはいけないことを先に書きます。AIが書いた中身はこの約束に照らして機械で確かめられ、守れていなければ書き直しになります。"),
    ("6", "決めていないことは tbd に", "まだ決めていないことは tbd に書いておけます。tbd が残っているあいだは <code>ponte check</code> が通らないので、決め忘れたまま動き出すことはありません。"),
]

HEAD = (HERE / "head.html").read_text(encoding="utf-8")
CSS = (HERE / "page.css").read_text(encoding="utf-8")        # 最後に </style> がある
DOCS_CSS = (HERE / "docs.css").read_text(encoding="utf-8")


def header(current: str) -> str:
    h = (HERE / "header.html").read_text(encoding="utf-8").replace("{REPO}", REPO).replace("{DOC}", DOC)
    for name in ("learn", "reference"):
        h = h.replace("{CUR_%s}" % name, ' aria-current="page"' if name == current else "")
    return h


SPY = """<script>
(() => {   // 目次の、いま読んでいる所に印を付ける
  const links = [...document.querySelectorAll(".toc a")], map = new Map(links.map(a => [a.hash.slice(1), a]));
  const io = new IntersectionObserver(es => es.forEach(e => {
    if(!e.isIntersecting) return;
    links.forEach(a => a.classList.remove("on")); const a = map.get(e.target.id); if(a) a.classList.add("on");
  }), {rootMargin: "0px 0px -70% 0px"});
  document.querySelectorAll(".prose h2[id], .prose h3[id], .prose section[id]").forEach(h => map.has(h.id) && io.observe(h));
})();
</script>"""


def page(title: str, current: str, body: str, extra_css: str = "") -> str:
    css = CSS if not extra_css else CSS.replace("</style>", extra_css + "\n</style>")
    return HEAD.replace("__TITLE__", html.escape(title)) + css + body.replace("{HEADER}", header(current)) + (SPY if extra_css else "")


# ---------------------------------------------------------------------------
# トップ
# ---------------------------------------------------------------------------

def landing() -> str:
    srcs = {n: (HERE / "samples" / f"{n}.ponte").read_text(encoding="utf-8") for n, _, _ in SLIDES}
    states = states_in("\n".join(srcs.values()))
    items = []
    for i, (n, h, p) in enumerate(SLIDES):
        hid = "" if i == 0 else " hidden"
        items.append(f'    <div class="slide"{hid}>\n      <pre class="code">{highlight(srcs[n], states)}</pre>\n'
                     f'      <div class="explain"><h2>{h}</h2><p>{p}</p></div>\n    </div>')
    dots = "".join('<button type="button" data-go="%d" aria-label="見本 %d"%s>%d</button>'
                   % (i, i + 1, ' aria-current="true"' if i == 0 else "", i + 1) for i in range(len(SLIDES)))
    body = (HERE / "page.body.html").read_text(encoding="utf-8")
    body = body.replace("{REPO}", REPO).replace("{DOC}", DOC).replace("{SLIDES}", "\n".join(items)).replace("{DOTS}", dots)
    return page("Ponte", "", body)


# ---------------------------------------------------------------------------
# 入門・読みもの
# ---------------------------------------------------------------------------

def link(url: str) -> str:
    """docs の中の相対リンクを、ホームページから行ける所に"""
    if url.startswith(("http", "#")):
        return url
    m = re.fullmatch(r"screenshots/(\w+)\.png", url)
    if m:
        return "{{IMG:%s}}" % m.group(1)
    if url == "入門.md":
        return "learn.html"
    if url.startswith("../"):
        return BLOB + url[3:]
    return DOC + url


def doc_page(md_path: Path, title: str, current: str) -> str:
    content, toc = render(md_path.read_text(encoding="utf-8"), link)
    content = re.sub(r"^<h1[^>]*>.*?</h1>\n", "", content)        # 見出しはページの上に出す
    content = content.replace("<p>", '<p class="lead">', 1)       # 最初の段落を、見出しの下の一文に
    nav = "".join(f'<li class="d{d}"><a href="#{i}">{html.escape(t)}</a></li>' for d, i, t in toc)
    body = f"""<div class="wrap">
{{HEADER}}
<div class="doc">
  <aside class="toc" aria-label="目次"><p class="toc-h">目次</p><ol>{nav}</ol></aside>
  <article class="prose">
    <p class="eyebrow">{html.escape(current.upper())}</p>
    <h1>{html.escape(title)}</h1>
{content}
  </article>
</div>
<footer><p>この入門の出力は、実際にコマンドを流したものです（テストで確かめています）。</p></footer>
</div>
"""
    return page(f"{title} — Ponte", current, body, DOCS_CSS)


# ---------------------------------------------------------------------------
# 道具とエラー（実装から）
# ---------------------------------------------------------------------------

def _code(s: str) -> str:
    return f"<code>{html.escape(s)}</code>"


def _table(head, rows) -> str:
    t = "<tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>"
    t += "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="table"><table>{t}</table></div>'


def _md(s: str) -> str:
    return inline(s, link)


def commands_section() -> str:
    from ponte.cli import build_parser
    p = build_parser()
    sub = next(a for a in p._actions if isinstance(a, argparse._SubParsersAction))
    rows = []
    for c in sub._choices_actions:
        sp = sub.choices[c.dest]
        def arg(a):
            name = "|".join(a.choices) if a.choices else a.dest
            return f"[{name}]" if a.nargs == "?" else f"{name}…" if a.nargs == "+" else name
        pos = " ".join(arg(a) for a in sp._actions if not a.option_strings)
        opts = "".join(f"<br>{_code(a.option_strings[-1])} {html.escape(a.help or '')}"
                       for a in sp._actions if a.option_strings and a.dest != "help" and a.help)
        rows.append((_code(f"ponte {c.dest} {pos}".strip()), html.escape(c.help) + opts))
    return _table(["コマンド", "すること"], rows)


def forms_section() -> str:
    from ponte.forms import DO_FORMS, VALUE_FORMS, WHEN_FORMS
    when = _table(["書き方", "意味"], [(_code(f[1]), _md(f[2])) for f in WHEN_FORMS if f[4]])
    later = " / ".join(_code(f[1]) for f in WHEN_FORMS if not f[4])
    do = _table(["書き方", "意味"], [(_code(f[1]), _md(f[2])) for f in DO_FORMS])
    val = _table(["書き方", "意味"], [(_code(f[1]), _md(f[2])) for f in VALUE_FORMS])
    return (f'<h3 id="when">when — きっかけ</h3><p>書けるのは出来事だけです。状態（「期限が近い」など）は where か list で絞ります。</p>{when}'
            f'<p class="note">書き方は決まっていて、まだ起きないもの（check で止まります）: {later}</p>'
            f'<h3 id="do">do — やること</h3><p>1つの rule でやることは1つだけです。2つあるときは rule を分けて relate の then でつなぎます。</p>{do}'
            f'<h3 id="values">値</h3><p>create の「項目 値」と set に書けるものです。</p>{val}')


def tools_section() -> str:
    from ponte.body import SHAPE_PARTS, TOOLS
    groups: dict[str, list] = {}
    for kind, form, meaning, expr, inp, want in TOOLS:
        ex = f'{_code(expr)}<span class="arrow"> t = {html.escape(repr(inp))} → </span>{_code(repr(want) if not isinstance(want, str) else want)}' if expr else "—"
        groups.setdefault(kind, []).append((_code(form), _md(meaning), ex))
    out = []
    for kind, rows in groups.items():
        out.append(f'<h3 id="tool-{html.escape(kind)}">{html.escape(kind)}</h3>' + _table(["書き方", "意味", "例（テストで動かしています）"], rows))
    shapes = _table(["部品", "意味"], [(_code(f), _md(m)) for f, m in SHAPE_PARTS])
    sample = """shape Deadline
  month digits 1..2
  "/"
  day digits 1..2
  maybe Clock

shape Clock
  space
  hour digits 1..2
  ":"
  minute digits 2"""
    return ("".join(out)
            + '<h3 id="shape">shape — 正規表現の代わり</h3><p>見出しの下に、部品を1行に1つずつ並べます。名前を付けた部分は <code>名前 of 当たり</code> で取り出せます。</p>'
            + shapes + f'<pre class="code">{highlight(sample, states_in(sample))}</pre>')


def std_section() -> str:
    from ponte.parser import STD_DIR
    rows = []
    for p in sorted(Path(STD_DIR).glob("*.ponte")):
        src = p.read_text(encoding="utf-8")
        about = src.splitlines()[0].lstrip("# ").split("—", 1)[-1].strip()
        acts = re.findall(r"^action (\w+)\n  in\s+(.+)\n  out\s+(.+)$", src, re.M)
        names = "<br>".join(f"{_code(a)} <span class='muted'>{html.escape(i)} → {html.escape(o)}</span>" for a, i, o in acts)
        rows.append((_code(f"use std/{p.stem}"), html.escape(about), names))
    return _table(["書き方", "中身", "action"], rows)


def errors_section() -> str:
    from ponte.errors import ERRORS
    items = []
    for c, title, why, fix in ERRORS:
        kind = "warn" if c.startswith("W") else "err"
        items.append(f'<div class="errcard" id="{c}"><p class="ehead"><span class="badge {kind}">{c}</span> {_md(title)}</p>'
                     f'<p><b>なぜ止めるか</b> {_md(why)}</p><p><b>どう直すか</b> {_md(fix)}</p></div>')
    return '<div class="errs">' + "".join(items) + "</div>"


def reference() -> str:
    sections = [
        ("commands", "コマンド", "<code>python -m ponte</code> か、<code>pip install -e .</code> のあとは <code>ponte</code> だけで使えます。", commands_section()),
        ("rules", "rule の書き方", "rule は、きっかけ（when）とやること（do）の一組です。", forms_section()),
        ("tools", "do で使える道具", "action の中身に書ける道具は、これで全部です。ここに無いものを書くとエラーになります。", tools_section()),
        ("std", "標準ライブラリ", "中身も Ponte で書かれていて、example が付いています。", std_section()),
        ("errors", "エラー", "<code>ponte check</code> が止める理由と直し方です。<code>ponte explain E32</code> でも同じものが見られます。", errors_section()),
    ]
    nav = "".join(f'<li class="d2"><a href="#{i}">{t}</a></li>' for i, t, _, _ in sections)
    body = "".join(f'<section class="ref" id="{i}"><h2>{t}</h2><p>{lead}</p>{inner}</section>' for i, t, lead, inner in sections)
    return page("道具とエラー — Ponte", "reference", f"""<div class="wrap">
{{HEADER}}
<div class="doc">
  <aside class="toc" aria-label="目次"><p class="toc-h">目次</p><ol>{nav}</ol></aside>
  <article class="prose">
    <p class="eyebrow">REFERENCE</p>
    <h1>道具とエラー</h1>
    <p class="lead">このページは Ponte の実装から作っています。道具の例は全部テストで動かしているので、ここに書いてあることはそのまま動きます。</p>
{body}
  </article>
</div>
<footer><p>v0.3 ・ Python 3.11</p></footer>
</div>
""", DOCS_CSS)


if __name__ == "__main__":
    (HERE / "landing.html").write_text(landing(), encoding="utf-8")
    (HERE / "learn.src.html").write_text(doc_page(ROOT / "docs" / "入門.md", "入門 — やることアプリを作る", "learn"), encoding="utf-8")
    (HERE / "reference.src.html").write_text(reference(), encoding="utf-8")
    print("site/landing.html・learn.src.html・reference.src.html を作りました")
