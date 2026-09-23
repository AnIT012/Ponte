"""ponte lsp: 本物の言語サーバーとして、標準入出力で話せる。"""
import json
import os
import subprocess
import sys


def frame(msg):
    b = json.dumps(msg).encode()
    return b"Content-Length: %d\r\n\r\n" % len(b) + b


def read_all(data: bytes):
    out = []
    while data:
        head, _, rest = data.partition(b"\r\n\r\n")
        n = int(head.split(b":")[1])
        out.append(json.loads(rest[:n]))
        data = rest[n:]
    return out


def test_lsp_diagnostics_hover_completion():
    path = os.path.abspath("tests/cases/E32_unknown_state/broken.ponte")
    uri = "file://" + path
    text = open(path, encoding="utf-8").read()
    line = next(i for i, l in enumerate(text.split("\n")) if "submited" in l)
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "textDocument/didOpen", "params": {"textDocument": {"uri": uri, "text": text}}},
        {"jsonrpc": "2.0", "id": 2, "method": "textDocument/hover", "params": {"textDocument": {"uri": uri}, "position": {"line": 0, "character": 0}}},
        {"jsonrpc": "2.0", "id": 3, "method": "textDocument/completion", "params": {"textDocument": {"uri": uri}, "position": {"line": line, "character": 4}}},
        {"jsonrpc": "2.0", "method": "textDocument/didChange", "params": {"textDocument": {"uri": uri}, "contentChanges": [{"text": text.replace("submited", "submitted")}]}},
        {"jsonrpc": "2.0", "id": 4, "method": "shutdown"},
        {"jsonrpc": "2.0", "method": "exit"},
    ]
    p = subprocess.run([sys.executable, "-m", "ponte", "lsp"], input=b"".join(frame(m) for m in msgs),
                       capture_output=True, timeout=30)
    assert p.returncode == 0, p.stderr
    got = read_all(p.stdout)
    assert got[0]["result"]["capabilities"]["hoverProvider"] is True
    diags = [m for m in got if m.get("method") == "textDocument/publishDiagnostics"]
    first = diags[0]["params"]["diagnostics"]
    assert [d["code"] for d in first] == ["E32"] and first[0]["range"]["start"]["line"] == line
    assert "もしかして submitted" in first[0]["message"] and "直し方" in first[0]["message"]
    assert diags[1]["params"]["diagnostics"] == []            # 直したら消える
    labels = {c["label"] for c in next(m for m in got if m.get("id") == 3)["result"]}
    assert {"submitted", "Application", "count of X"} <= labels


def test_hover_explains_codes_and_heads():
    from ponte.lsp import hover
    assert "tbd" in hover("# E05 のこと", 0, 3)
    assert "データの形" in hover("thing Task", 0, 2)
