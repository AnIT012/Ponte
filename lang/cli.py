"""CLI（仕様 v0.2）。

  python -m lang check spec/hub.lang               決めてないことを探す
  python -m lang check spec/hub.lang --publish     公開する時の検査（読み上げ対応もエラー）
  python -m lang check spec/hub.lang --save-shape  通ったら thing の形を <spec>.shape.json に残す（次の change 検査に使う）
  python -m lang test  spec/hub_app.lang           rule の example を全部流す
  python -m lang run   spec/hub_app.lang           動かす（ブラウザで http://127.0.0.1:8000/）
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .checker import Options, check, shape_of
from .parser import ParseError, parse_file


def shape_path(spec_path: str) -> str:
    return spec_path + ".shape.json"


def cmd_check(args) -> int:
    try:
        spec = parse_file(args.spec)
    except ParseError as e:
        print("読めません（1件）")
        print(f"  - {e}")
        return 2
    except FileNotFoundError:
        print(f"ファイルがありません: {args.spec}")
        return 2
    prev = None
    if os.path.exists(shape_path(args.spec)):
        with open(shape_path(args.spec), encoding="utf-8") as f:
            prev = json.load(f)
    findings = check(spec, Options(publish=args.publish, prev_shape=prev))
    errors = [f for f in findings if f.is_error]
    warnings = [f for f in findings if not f.is_error]
    if errors:
        print(f"渡せません（{len(errors)}件）")
        for f in errors:
            print(f"  - {f}")
    else:
        print("決めてないことなし。AIに渡せます")
        if args.save_shape:
            with open(shape_path(args.spec), "w", encoding="utf-8") as f:
                json.dump(shape_of(spec), f, ensure_ascii=False, indent=2, sort_keys=True)
            print(f"thing の形を残しました: {shape_path(args.spec)}")
    if warnings:
        print(f"注意（{len(warnings)}件）")
        for f in warnings:
            print(f"  - {f}")
    return 1 if errors else 0


def _load_checked(path: str):
    """読んで、チェックを通ったものだけ返す。通らなければ理由を出して None。"""
    try:
        spec = parse_file(path)
    except (ParseError, FileNotFoundError) as e:
        print(f"読めません: {e}")
        return None
    errors = [f for f in check(spec) if f.is_error]
    if errors:
        print(f"渡せません（{len(errors)}件）。先に check を通してください")
        for f in errors:
            print(f"  - {f}")
        return None
    return spec


def cmd_test(args) -> int:
    from .examples import run_examples
    spec = _load_checked(args.spec)
    if spec is None:
        return 1
    results = run_examples(spec)
    bad = [r for r in results if not r.ok]
    for r in results:
        print(f"  {'通過' if r.ok else '失敗'}  rule {r.rule}（L{r.line}）{'' if r.ok else ': ' + r.message}")
    print(f"example {len(results)}件中 {len(results) - len(bad)}件通過")
    return 1 if bad else 0


def cmd_run(args) -> int:
    from .runtime import Engine
    from .server import serve
    spec = _load_checked(args.spec)
    if spec is None:
        return 1
    store = args.data or (args.spec + ".data.jsonl")
    httpd = serve(spec, Engine(spec, store=store), port=args.port, host=args.host)
    print(f"動いています: http://{args.host}:{args.port}/   （データ: {store}、止めるのは Ctrl+C）")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m lang", description="人とAIの間の言語（名前未定）v0.2")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="決めてないことを探す")
    c.add_argument("spec")
    c.add_argument("--publish", action="store_true", help="公開する時の検査")
    c.add_argument("--save-shape", action="store_true", help="通ったら thing の形を残す")
    c.set_defaults(fn=cmd_check)
    t = sub.add_parser("test", help="rule の example を全部流す")
    t.add_argument("spec")
    t.set_defaults(fn=cmd_test)
    r = sub.add_parser("run", help="動かす（ブラウザで開く）")
    r.add_argument("spec")
    r.add_argument("--port", type=int, default=8000)
    r.add_argument("--host", default="127.0.0.1")
    r.add_argument("--data", help="データを残すファイル（既定は <spec>.data.jsonl）")
    r.set_defaults(fn=cmd_run)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
