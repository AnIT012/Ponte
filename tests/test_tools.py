"""build（1つのファイル）とエディタの色分けのテスト。"""
import json
import re
import subprocess
import sys

from ponte.build import build


import pytest


@pytest.mark.parametrize("spec", ["spec/hub_app.ponte", "spec/kakeibo.ponte"])     # kakeibo は std を使う
def test_build_single_file_runs_check_and_test(tmp_path, spec):
    out = tmp_path / "app.pyz"
    build(spec, str(out))
    for cmd in (["check"], ["test"]):
        r = subprocess.run([sys.executable, str(out), *cmd], capture_output=True, text=True, cwd=tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
    assert "失敗" not in r.stdout and "件通過" in r.stdout


def test_editor_grammar_is_valid():
    g = json.load(open("editor/vscode/syntaxes/ponte.tmLanguage.json", encoding="utf-8"))
    for p in g["patterns"]:
        re.compile(p["match"])
    pkg = json.load(open("editor/vscode/package.json", encoding="utf-8"))
    assert pkg["contributes"]["languages"][0]["extensions"] == [".ponte"]
    decl = next(p for p in g["patterns"] if p["name"] == "keyword.declaration.ponte")
    assert re.search(decl["match"], "thing Application") and not re.search(decl["match"], "  where x is y")
