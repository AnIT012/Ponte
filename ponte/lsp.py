"""`ponte lsp` — エディタ向けの言語サーバー（Language Server Protocol。標準入出力。依存なし）。

できること:
  - 開いた・書き換えた・保存した時に check を流して、エラーを出す（直し方つき）
  - エラーのコード（E32 など）や見出しの言葉に乗せると説明が出る（hover）
  - 見出し・thing の名前・状態の名前・道具の書き方を補う（completion）

エディタの設定では、コマンドを `python -m ponte lsp` にするだけ。
"""
from __future__ import annotations

import json
import os
import re
import sys
from urllib.parse import unquote, urlparse

from .checker import check
from .errors import BY_CODE
from .parser import ParseError, parse, parse_file

HEADS = {
    "thing": "データの形（項目の名前と型の一覧）",
    "flow": "状態の流れ（`a -> b`）と、競合したときの優先順位（`a > b`）",
    "who": "誰が何をできるか（書いていない操作は誰にもできない）",
    "list": "条件で絞った一覧（of / where / sort）",
    "rule": "きっかけ（when）と処理（do）の組み合わせ（example で確認）",
    "relate": "rule 同士の関係（then / then no / before / > / else）",
    "action": "AI の担当部分（example、never、else による約束付き）",
    "match": "値ごとの結果",
    "scene": "画面", "look": "一覧の見せ方", "part": "自分で作る部品", "input": "入力",
    "style": "見た目", "words": "画面の文字（言語ごと）", "shape": "正規表現の代わり",
    "tbd": "まだ決めていないこと（残っていると実行できない）", "use": "別のファイルか標準ライブラリの読み込み",
    "change": "thing の形を変えたときのデータの移行方法", "connect": "外部サービスとの接続", "group": "まとまり",
}


def _read(stream) -> dict | None:
    length = 0
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.decode("ascii", "replace").strip()
        if not line:
            break
        k, _, v = line.partition(":")
        if k.lower() == "content-length":
            length = int(v.strip())
    return json.loads(stream.read(length).decode("utf-8"))


def _write(stream, msg: dict) -> None:
    body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    stream.flush()


def _path(uri: str) -> str:
    return unquote(urlparse(uri).path)


def diagnostics(text: str, path: str) -> list[dict]:
    """check の結果を LSP の診断に。use した別ファイルのエラーは、このファイルの use の行に出す"""
    here = os.path.abspath(path)
    try:
        spec = parse_file(path, text=text)
        findings = check(spec)
    except ParseError as e:
        return [_diag(e.line, "E00", e.message, True, text)]
    out = []
    for f in findings:
        p, line = spec.where(f.line)
        if os.path.abspath(p) != here:
            use = next((d.line for d in spec.roots if d.keyword == "use"), 1)
            line, f_msg = use, f"{os.path.basename(p)}:{line}  {f.message}"
        else:
            f_msg = f.message
        e = BY_CODE.get(f.code)
        out.append(_diag(line, f.code, f_msg + (f"\n直し方: {e[3]}" if e else ""), f.is_error, text))
    return out


def _diag(line: int, code: str, msg: str, error: bool, text: str) -> dict:
    lines = text.split("\n")
    i = max(0, min(line - 1, len(lines) - 1))
    s = len(lines[i]) - len(lines[i].lstrip()) if lines else 0
    return {"range": {"start": {"line": i, "character": s}, "end": {"line": i, "character": len(lines[i]) if lines else 0}},
            "severity": 1 if error else 2, "code": code, "source": "ponte", "message": msg}


def _word_at(text: str, line: int, ch: int) -> str:
    lines = text.split("\n")
    if line >= len(lines):
        return ""
    l = lines[line]
    for m in re.finditer(r"[A-Za-z_][\w-]*", l):
        if m.start() <= ch <= m.end():
            return m.group(0)
    return ""


def hover(text: str, line: int, ch: int) -> str | None:
    w = _word_at(text, line, ch)
    if re.fullmatch(r"[EW]\d\d", w) and w in BY_CODE:
        c, title, why, fix = BY_CODE[w]
        return f"**{c} {title}**\n\nなぜ止めるか: {why}\n\nどう直すか: {fix}"
    if w in HEADS:
        return f"**{w}**: {HEADS[w]}"
    from .body import TOOLS
    for kind, form, meaning, *_ in TOOLS:
        if form.split()[0] == w:
            return f"`{form}`（{kind}）: {meaning}"
    return None


def completions(text: str, line: int) -> list[dict]:
    items = []
    lines = text.split("\n")
    cur = lines[line] if line < len(lines) else ""
    if not cur.startswith((" ", "\t")):
        items += [{"label": h, "kind": 14, "detail": d} for h, d in HEADS.items()]
    try:
        spec = parse(text)
        names = {d.name for d in spec.decls() if d.name}
        states = set()
        for t in spec.decls("thing"):
            for c in t.children:
                m = re.match(r"^\[([^\]]*)\]", c.text.strip())
                if m:
                    states |= {s.strip() for s in m.group(1).split("|") if s.strip()}
    except ParseError:
        names, states = set(), set()
    items += [{"label": n, "kind": 7} for n in sorted(names)]
    items += [{"label": s, "kind": 20} for s in sorted(states)]
    if cur.startswith((" ", "\t")):
        from .body import TOOLS
        items += [{"label": form.split(" / ")[0], "kind": 3, "detail": meaning} for _, form, meaning, *_ in TOOLS]
    return items


def serve(inp=None, out=None) -> int:
    inp = inp or sys.stdin.buffer
    out = out or sys.stdout.buffer
    docs: dict[str, str] = {}

    def publish(uri: str):
        _write(out, {"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics",
                     "params": {"uri": uri, "diagnostics": diagnostics(docs[uri], _path(uri))}})

    while True:
        try:
            msg = _read(inp)
        except (ValueError, UnicodeDecodeError, RecursionError):   # 読めない1通は捨てて続ける
            continue
        if msg is None:
            return 0
        if not isinstance(msg, dict):
            continue
        method, mid, p = msg.get("method"), msg.get("id"), msg.get("params") or {}
        if not isinstance(p, dict):
            p = {}
        try:
            if method == "initialize":
                _write(out, {"jsonrpc": "2.0", "id": mid, "result": {
                    "capabilities": {"textDocumentSync": 1, "hoverProvider": True,
                                     "completionProvider": {"triggerCharacters": [" "]}},
                    "serverInfo": {"name": "ponte"}}})
            elif method == "shutdown":
                _write(out, {"jsonrpc": "2.0", "id": mid, "result": None})
            elif method == "exit":
                return 0
            elif method == "textDocument/didOpen":
                d = p["textDocument"]
                docs[d["uri"]] = d["text"]
                publish(d["uri"])
            elif method == "textDocument/didChange":
                uri = p["textDocument"]["uri"]
                docs[uri] = p["contentChanges"][-1]["text"]
                publish(uri)
            elif method == "textDocument/didSave":
                publish(p["textDocument"]["uri"])
            elif method == "textDocument/didClose":
                docs.pop(p["textDocument"]["uri"], None)
            elif method == "textDocument/hover":
                pos, uri = p["position"], p["textDocument"]["uri"]
                h = hover(docs.get(uri, ""), pos["line"], pos["character"])
                _write(out, {"jsonrpc": "2.0", "id": mid,
                             "result": {"contents": {"kind": "markdown", "value": h}} if h else None})
            elif method == "textDocument/completion":
                pos, uri = p["position"], p["textDocument"]["uri"]
                _write(out, {"jsonrpc": "2.0", "id": mid, "result": completions(docs.get(uri, ""), pos["line"])})
            elif mid is not None:
                _write(out, {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"not supported: {method}"}})
        except Exception as e:           # 1つの要求で壊れても、サーバーは止めない
            if mid is not None:
                _write(out, {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}})
