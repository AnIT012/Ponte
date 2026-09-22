"""CLI（仕様 v0.2）。

  python -m lang check spec/hub.lang               決めてないことを探す
  python -m lang check spec/hub.lang --publish     公開する時の検査（読み上げ対応もエラー）
  python -m lang check spec/hub.lang --save-shape  通ったら thing の形を <spec>.shape.json に残す（次の change 検査に使う）
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m lang", description="人とAIの間の言語（名前未定）v0.2")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="決めてないことを探す")
    c.add_argument("spec")
    c.add_argument("--publish", action="store_true", help="公開する時の検査")
    c.add_argument("--save-shape", action="store_true", help="通ったら thing の形を残す")
    c.set_defaults(fn=cmd_check)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
