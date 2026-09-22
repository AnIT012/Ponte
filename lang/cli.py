"""CLI。  python -m lang check spec/hub.spec"""
from __future__ import annotations

import argparse
import sys

from .checker import check
from .parser import ParseError, parse_file


def cmd_check(args) -> int:
    try:
        spec = parse_file(args.spec)
    except ParseError as e:
        print(f"読めません（1件）")
        print(f"  - {e}")
        return 2
    except FileNotFoundError:
        print(f"ファイルがありません: {args.spec}")
        return 2

    findings = check(spec)
    errors = [f for f in findings if f.is_error]
    warnings = [f for f in findings if not f.is_error]

    if errors:
        print(f"渡せません（{len(errors)}件）")
        for f in errors:
            print(f"  - {f}")
    else:
        print("決めてないことなし。AIに渡せます")
    if warnings:
        print(f"注意（{len(warnings)}件）")
        for f in warnings:
            print(f"  - {f}")
    return 1 if errors else 0


def cmd_gen(args) -> int:
    from .codegen import generate_to_dir
    try:
        spec = parse_file(args.spec)
    except ParseError as e:
        print(f"読めません: {e}")
        return 2
    errors = [f for f in check(spec) if f.is_error]
    if errors:
        print(f"渡せません（{len(errors)}件）。先に check を通してください")
        for f in errors:
            print(f"  - {f}")
        return 1
    files = generate_to_dir(spec, args.out, package=args.package)
    for p in files:
        print(f"書きました: {p}")
    return 0


def cmd_proposals(args) -> int:
    from .proposals import list_proposals
    try:
        spec = parse_file(args.spec)
    except ParseError as e:
        print(f"読めません: {e}")
        return 2
    items = list_proposals(spec)
    if not items:
        print("承認待ちの提案はありません")
        return 0
    print(f"承認待ち（{len(items)}件）")
    for it in items:
        print(f"  - {it}")
    return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m lang", description="人とAIの間の言語（名前未定）")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="決めてないことを探す")
    c.add_argument("spec")
    c.set_defaults(fn=cmd_check)

    g = sub.add_parser("gen", help="決まった部分を Go に変換する")
    g.add_argument("spec")
    g.add_argument("-o", "--out", required=True, help="出力ディレクトリ")
    g.add_argument("--package", default="hub")
    g.set_defaults(fn=cmd_gen)

    pr = sub.add_parser("proposals", help="AIの提案（proposed）で承認待ちのものを一覧する")
    pr.add_argument("spec")
    pr.set_defaults(fn=cmd_proposals)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
