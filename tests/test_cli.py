"""コマンドを1つずつ、本当に動かす（読めない・無い・通らない時の出方も）。"""
import io
import json
import shutil

from ponte.cli import main


def copy(tmp_path, name="todo"):
    p = tmp_path / f"{name}.ponte"
    shutil.copy(f"spec/{name}.ponte", p)
    return str(p)


def test_check_outputs(tmp_path, capsys):
    assert main(["check", "spec/todo.ponte"]) == 0
    assert "決めていないことはありません" in capsys.readouterr().out
    assert main(["check", str(tmp_path / "none.ponte")]) == 2
    assert "ありません" in capsys.readouterr().out
    bad = tmp_path / "bad.ponte"
    bad.write_text("thing A\n   x text\n  y text\n", encoding="utf-8")
    assert main(["check", str(bad)]) in (1, 2)
    p = copy(tmp_path)
    assert main(["check", p, "--save-shape"]) == 0
    assert (tmp_path / "todo.ponte.shape.json").exists()


def test_test_new_fmt_build_role(tmp_path, capsys, monkeypatch):
    assert main(["test", "spec/todo.ponte", "--strict"]) == 0
    assert "通過" in capsys.readouterr().out
    assert main(["test", "tests/cases/E32_unknown_state/broken.ponte"]) == 1
    monkeypatch.chdir(tmp_path)
    assert main(["new", "myapp"]) == 0 and (tmp_path / "myapp.ponte").exists()
    assert main(["new", "myapp"]) == 1                          # 上書きしない
    assert main(["check", "myapp.ponte"]) == 0
    assert main(["fmt", "--check", "myapp.ponte"]) == 0
    messy = tmp_path / "messy.ponte"
    import re
    src = (tmp_path / "myapp.ponte").read_text(encoding="utf-8")
    messy.write_text(re.sub(r"(?m)^(  \S+) {2,}", r"\1 ", src), encoding="utf-8")   # 揃えた空白を崩す
    assert main(["fmt", "--check", str(messy)]) == 1
    assert main(["fmt", str(messy)]) == 0
    assert main(["fmt", "--check", str(messy)]) == 0
    assert main(["build", "myapp.ponte", "-o", "app.pyz"]) == 0 and (tmp_path / "app.pyz").exists()


def test_role(tmp_path, capsys):
    p = copy(tmp_path, "lend")
    assert main(["role", p, "taro", "admin"]) == 0
    assert main(["role", p, "taro", "king"]) == 1
    assert "king" in capsys.readouterr().out
    t = copy(tmp_path, "todo")
    assert main(["role", t, "taro", "admin"]) == 1              # role の無いアプリ


def test_explain_list_and_guides(capsys):
    assert main(["explain"]) == 0
    out = capsys.readouterr().out
    assert "E01" in out and "E32" in out
    assert main(["guide"]) == 0 and "道具" in capsys.readouterr().out
    assert main(["guide", "--rules"]) == 0 and "when" in capsys.readouterr().out


def test_lsp_in_process():
    from ponte.lsp import serve

    def frame(m):
        b = json.dumps(m).encode()
        return b"Content-Length: %d\r\n\r\n" % len(b) + b
    uri = "file:///tmp/x.ponte"
    text = "thing Task\n  title text\n"
    msgs = [{"id": 1, "method": "initialize"}, {"method": "textDocument/didOpen", "params": {"textDocument": {"uri": uri, "text": text}}},
            {"id": 2, "method": "textDocument/hover", "params": {"textDocument": {"uri": uri}, "position": {"line": 0, "character": 1}}},
            {"id": 3, "method": "textDocument/completion", "params": {"textDocument": {"uri": uri}, "position": {"line": 1, "character": 2}}},
            {"id": 4, "method": "nope"}, {"method": "textDocument/didSave", "params": {"textDocument": {"uri": uri}}},
            {"method": "textDocument/didClose", "params": {"textDocument": {"uri": uri}}}, {"id": 5, "method": "shutdown"}, {"method": "exit"}]
    out = io.BytesIO()
    assert serve(io.BytesIO(b"".join(frame({"jsonrpc": "2.0", **m}) for m in msgs)), out) == 0
    data, got = out.getvalue(), []
    while data:
        head, _, rest = data.partition(b"\r\n\r\n")
        n = int(head.split(b":")[1])
        got.append(json.loads(rest[:n]))
        data = rest[n:]
    by_id = {m.get("id"): m for m in got if "id" in m}
    assert "データの形" in by_id[2]["result"]["contents"]["value"]
    assert any(c["label"] == "Task" for c in by_id[3]["result"])
    assert by_id[4]["error"]["code"] == -32601
    diags = [m for m in got if m.get("method") == "textDocument/publishDiagnostics"]
    assert diags and any(d["code"] == "E19" for d in diags[0]["params"]["diagnostics"])


def test_lsp_survives_garbage():
    from ponte.lsp import serve

    def raw(body: bytes, length=None):
        return b"Content-Length: %s\r\n\r\n" % (str(len(body) if length is None else length).encode()) + body
    good = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}).encode()
    stream = raw(b"[]") + raw(b"{not json") + raw(b'"str"') + raw(good)
    out = io.BytesIO()
    assert serve(io.BytesIO(stream), out) == 0
    assert b'"id": 1' in out.getvalue()


def test_new_from_sample(tmp_path, monkeypatch, capsys):
    import filecmp
    for n in ("todo", "lend", "kakeibo"):                    # ひな形は見本のアプリと同じ中身
        assert filecmp.cmp(f"spec/{n}.ponte", f"ponte/templates/{n}.ponte", shallow=False), f"python: cp spec/{n}.ponte ponte/templates/"
    monkeypatch.chdir(tmp_path)
    assert main(["new", "rental", "--from", "lend"]) == 0
    assert main(["check", "rental.ponte"]) == 0
    assert main(["new", "x", "--from", "nope"]) == 1
    assert "lend" in capsys.readouterr().out


def test_pyz_keeps_data_next_to_itself(tmp_path):
    """1つのファイル（.pyz）: 一時フォルダではなく、自分の隣にデータとログインの人を残す（動かし直しても消えない）"""
    import os
    import subprocess
    import sys
    out = tmp_path / "app.pyz"
    assert main(["build", "spec/todo.ponte", "-o", str(out)]) == 0
    env = {**os.environ, "PONTE_PASSWORD": "long-enough"}
    env.pop("PONTE_DATA_DIR", None)
    run = lambda *a: subprocess.run([sys.executable, str(out), *a], capture_output=True, text=True, env=env, cwd=tmp_path, timeout=60)
    assert run("check").returncode == 0
    r = run("user", "add", "taro")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / "todo.ponte.users.json").exists()
    assert "taro" in run("user", "list").stdout
