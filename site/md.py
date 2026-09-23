"""docs/ の Markdown を、ホームページ用の HTML にする（依存なし。docs で使っている書き方だけ）。

見出し・段落・箇条書き・番号付き・表・コード・引用・横線・画像・リンク・太字・`コード`。
コードは、Ponte なら highlight で色を付け、`$` で始まるもの（コマンドと出力）は端末の見た目にする。
"""
import html
import re

from highlight import highlight, states_in


def slug(text: str) -> str:
    t = re.sub(r"<[^>]+>", "", text)
    t = re.sub(r"[^\w぀-ヿ一-鿿-]+", "-", t).strip("-").lower()
    return t or "s"


def inline(text: str, link) -> str:
    parts = re.split(r"(`[^`]+`)", text)
    out = []
    for p in parts:
        if p.startswith("`") and p.endswith("`") and len(p) > 1:
            out.append(f"<code>{html.escape(p[1:-1])}</code>")
            continue
        s = html.escape(p, quote=False)
        s = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", lambda m: f'<img src="{link(m.group(2))}" alt="{m.group(1)}" loading="lazy">', s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<a href="{link(m.group(2))}">{m.group(1)}</a>', s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        out.append(s)
    return "".join(out)


def is_ponte(code: str) -> bool:
    first = next((l for l in code.splitlines() if l.strip()), "")
    return not first.startswith("$") and bool(re.match(r"^(thing|flow|list|match|rule|relate|action|who|scene|look|part|input|words|shape|use|change|connect|style|group|tbd|#)\b", first))


def code_block(code: str, lang: str, states) -> str:
    if lang in ("", "ponte", "lang") and is_ponte(code):
        return f'<pre class="code">{highlight(code, states)}</pre>'
    rows = []
    for l in code.split("\n"):
        e = html.escape(l)
        if l.startswith("$ "):
            e = f'<span class="prompt">$</span> {html.escape(l[2:])}'
        elif re.search(r"\bE\d\d\b", l):
            e = re.sub(r"\b(E\d\d)\b", r'<span class="ecode">\1</span>', e)
        rows.append(e)
    body = "\n".join(rows)
    return f'<pre class="term">{body}</pre>'


def render(src: str, link=lambda u: u) -> tuple[str, list[tuple[int, str, str]]]:
    """(HTML, 目次 [(深さ, id, 見出し)])"""
    lines = src.split("\n")
    states = states_in("\n".join(re.findall(r"```[^\n]*\n(.*?)```", src, re.S)))
    out, toc, i, para = [], [], 0, []

    def flush():
        if para:
            text = para[0]
            for nxt in para[1:]:       # 日本語どうしの改行は、つなぐ時に空白を入れない
                cjk = re.search(r"[\u3000-\u9fff\uff00-\uffef]$", text) and re.match(r"[\u3000-\u9fff\uff00-\uffef]", nxt)
                text += ("" if cjk else " ") + nxt
            out.append(f"<p>{inline(text, link)}</p>")
            para.clear()

    while i < len(lines):
        l = lines[i]
        if l.startswith("```"):
            flush()
            lang, j = l[3:].strip(), i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append(code_block("\n".join(lines[i + 1:j]), lang, states))
            i = j + 1
            continue
        if l.strip().startswith("<!--"):          # 自動の所の印（見せない）
            flush()
            i += 1
            continue
        m = re.match(r"^(#{1,4}) (.+)$", l)
        if m:
            flush()
            d, text = len(m.group(1)), inline(m.group(2), link)
            hid = slug(text)
            if d in (2, 3):
                toc.append((d, hid, re.sub(r"<[^>]+>", "", text)))
            out.append(f'<h{d} id="{hid}">{text}</h{d}>')
            i += 1
            continue
        if re.match(r"^-{3,}$", l.strip()):
            flush()
            out.append("<hr>")
            i += 1
            continue
        if l.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            cells = [[c.strip() for c in re.split(r"(?<!\\)\|", r.strip())[1:-1]] for r in rows]
            head, body = cells[0], [c for c in cells[1:] if not all(re.fullmatch(r":?-+:?", x) for x in c)]
            t = "<tr>" + "".join(f"<th>{inline(c.replace(chr(92) + '|', '|'), link)}</th>" for c in head) + "</tr>"
            t += "".join("<tr>" + "".join(f"<td>{inline(c.replace(chr(92) + '|', '|'), link)}</td>" for c in r) + "</tr>" for r in body)
            out.append(f'<div class="table"><table>{t}</table></div>')
            continue
        m = re.match(r"^(\s*)([-*]|\d+\.) (.+)$", l)
        if m:
            flush()
            tag = "ol" if m.group(2)[0].isdigit() else "ul"
            items = []
            while i < len(lines):
                m2 = re.match(r"^\s*([-*]|\d+\.) (.+)$", lines[i])
                if m2:
                    items.append(m2.group(2))
                elif lines[i].startswith("  ") and lines[i].strip() and items:
                    items[-1] += " " + lines[i].strip()
                else:
                    break
                i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x, link)}</li>" for x in items) + f"</{tag}>")
            continue
        if l.startswith("> "):
            flush()
            q = []
            while i < len(lines) and lines[i].startswith(">"):
                q.append(lines[i][1:].strip())
                i += 1
            out.append(f"<blockquote>{inline(' '.join(q), link)}</blockquote>")
            continue
        if not l.strip():
            flush()
        else:
            para.append(l.strip())
        i += 1
    flush()
    return "\n".join(out), toc
