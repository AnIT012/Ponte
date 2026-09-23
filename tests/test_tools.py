"""build（1つのファイル）とエディタの色分けのテスト。"""
import json
import re
import subprocess
import sys

from lang.build import build


def test_build_single_file_runs_check_and_test(tmp_path):
    out = tmp_path / "hub.pyz"
    build("spec/hub_app.lang", str(out))
    for cmd in (["check"], ["test"]):
        r = subprocess.run([sys.executable, str(out), *cmd], capture_output=True, text=True, cwd=tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
    assert "失敗" not in r.stdout and "件通過" in r.stdout


def test_editor_grammar_is_valid():
    g = json.load(open("editor/vscode/syntaxes/lang.tmLanguage.json", encoding="utf-8"))
    for p in g["patterns"]:
        re.compile(p["match"])
    pkg = json.load(open("editor/vscode/package.json", encoding="utf-8"))
    assert pkg["contributes"]["languages"][0]["extensions"] == [".lang"]
    decl = next(p for p in g["patterns"] if p["name"] == "keyword.declaration.lang")
    assert re.search(decl["match"], "thing Application") and not re.search(decl["match"], "  where x is y")
