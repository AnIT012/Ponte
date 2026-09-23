"""1つのファイルに固める（python -m ponte build spec/hub_app.ponte -o hub.pyz）。

spec と、AIが書いた中身（x.ponte.ai/）と、言語の実行エンジンを1つの .pyz にまとめる。
Python があればどこでも `python hub.pyz`（= run）/ `python hub.pyz check` / `python hub.pyz test` で動く。依存は無い。
"""
from __future__ import annotations

import shutil
import tempfile
import zipapp
from pathlib import Path

MAIN = '''import os, sys, tempfile, zipfile
# .pyz の中の spec を一時フォルダへ出してから、ふつうに動かす
here = os.path.dirname(os.path.abspath(__file__))
if zipfile.is_zipfile(here):
    out = tempfile.mkdtemp(prefix="ponte-app-")
    with zipfile.ZipFile(here) as z:
        for n in z.namelist():
            if n.startswith(("app/", "ponte/std/")):     # 標準ライブラリ（use std/...）も外へ
                z.extract(n, out)
    spec = os.path.join(out, "app", {spec!r})
    import ponte.parser
    ponte.parser.STD_DIR = os.path.join(out, "ponte", "std")
else:
    spec = os.path.join(here, "app", {spec!r})
from ponte.cli import main
args = sys.argv[1:] or ["run"]
sys.exit(main([args[0], spec] + args[1:]))
'''


def build(spec_path: str, out_path: str) -> str:
    spec = Path(spec_path)
    root = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        shutil.copytree(root, d / "ponte", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (d / "app").mkdir()
        shutil.copy(spec, d / "app" / spec.name)
        ai = Path(str(spec) + ".ai")
        if ai.is_dir():
            shutil.copytree(ai, d / "app" / ai.name)
        (d / "__main__.py").write_text(MAIN.format(spec=spec.name), encoding="utf-8")
        zipapp.create_archive(d, out_path, interpreter="/usr/bin/env python3")
    return out_path
