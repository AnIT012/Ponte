"""CLI（仕様 v0.2）。

  python -m ponte check spec/hub.ponte               決めてないことを探す
  python -m ponte check spec/hub.ponte --publish     公開する時の検査（読み上げ対応もエラー）
  python -m ponte check spec/hub.ponte --save-shape  通ったら thing の形を <spec>.shape.json に残す（次の change 検査に使う）
  python -m ponte test  spec/hub_app.ponte           rule の example を全部流す（確かめていない所も出す。--strict で失敗に）
  python -m ponte fill  spec/hub_app.ponte           by ai の action の中身をAIに書かせる
  python -m ponte run   spec/hub_app.ponte           動かす（ブラウザで http://127.0.0.1:8000/）
  python -m ponte new  myapp                       ひな形から新しいアプリを作る
  python -m ponte guide                            AIに渡す書き方の説明（実装から作る。--spec で仕様書の表も）
  python -m ponte role  spec/lend.ponte taro admin   最初の管理者を決める（2人目からは画面で）
  python -m ponte explain E32                      エラーの意味と直し方
  python -m ponte user add spec/lend.ponte taro      ログインする人を足す（ponte run --login）
  python -m ponte data export spec/todo.ponte        保存したデータを JSON で（--csv DIR で CSV）。compact で記録を詰める
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


def users_path(spec_path: str) -> str:
    return spec_path + ".users.json"


def cmd_check(args) -> int:
    try:
        spec = parse_file(args.spec)
    except ParseError as e:
        print("読めません（1件）")
        print(f"  {args.spec}:{e.line}  {e.message}")
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
    if args.json:
        from .errors import BY_CODE
        rows = []
        for f in findings:
            path, line = spec.where(f.line)
            e = BY_CODE.get(f.code)
            rows.append({"code": f.code, "file": path, "line": line, "message": f.message, "error": f.is_error,
                         "fix": e[3] if e else None})
        print(json.dumps({"ok": not errors, "findings": rows}, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    if errors:
        print(f"渡せません（{len(errors)}件）")
        for f in errors:
            path, line = spec.where(f.line)
            print(f"  {path}:{line}  {f.code}  {f.message}")
        print(f"  （直し方: ponte explain {errors[0].code}）")
    else:
        print("決めてないことなし。AIに渡せます")
        if args.save_shape:
            with open(shape_path(args.spec), "w", encoding="utf-8") as f:
                json.dump(shape_of(spec), f, ensure_ascii=False, indent=2, sort_keys=True)
            print(f"thing の形を残しました: {shape_path(args.spec)}")
    if warnings:
        print(f"注意（{len(warnings)}件）")
        for f in warnings:
            path, line = spec.where(f.line)
            print(f"  {path}:{line}  {f.code}  {f.message}")
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
        kind = "action" if r.rule in {a.name for a in spec.decls("action")} else "rule"
        path, line = spec.where(r.line)
        at = f"L{line}" if path == spec.path else f"{os.path.relpath(path)}:{line}"
        print(f"  {'通過' if r.ok else '失敗'}  {kind} {r.rule}（{at}）{'' if r.ok else ': ' + r.message}")
    print(f"example {len(results)}件中 {len(results) - len(bad)}件通過")
    from .examples import holes
    hs = holes(spec, results)
    if hs:
        print(f"穴（example で確かめていない所 {len(hs)}件）")
        for h in hs:
            path, line = spec.where(h.line)
            print(f"  {path}:{line}  {h.message}")
    if bad:
        return 1
    return 1 if hs and args.strict else 0


def cmd_run(args) -> int:
    from .runtime import Engine
    from .server import serve
    spec = _load_checked(args.spec)
    if spec is None:
        return 1
    store = args.data or (args.spec + ".data.jsonl")
    auth = None
    if args.login or args.signup:
        from .auth import Users
        from .server import Auth
        users = Users(users_path(args.spec))
        if not users.data and not args.signup:
            print(f"まだ誰も登録していません。先に: ponte user add {args.spec} 名前（か --signup で画面から登録）")
            return 1
        auth = Auth(users, signup=args.signup)
    elif args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"{args.host} で開くと、URL の ?user= で誰にでもなれてしまいます。外に出すなら --login を付けてください")
        return 1
    httpd = serve(spec, Engine(spec, store=store), port=args.port, host=args.host, auth=auth)
    if args.reload:
        import threading
        threading.Thread(target=watch, args=(args.spec, store, httpd.app), daemon=True).start()
    print(f"動いています: http://{args.host}:{args.port}/   （データ: {store}、止めるのは Ctrl+C）"
          + ("\n  ログインあり（" + ("画面から登録できる" if args.signup else "登録は ponte user add") + "）" if auth else ""))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def watched_files(spec_path: str, spec) -> dict[str, float]:
    """読み直しの見張り: spec と use したファイル、AIが書いた中身（<spec>.ai/）"""
    files = {f for _, f, _ in (spec.line_map or [])} | {spec_path}
    ai = spec_path + ".ai"
    if os.path.isdir(ai):
        files |= {os.path.join(ai, n) for n in os.listdir(ai)}
    return {f: os.path.getmtime(f) for f in files if os.path.exists(f)}


def reload_once(spec_path: str, store: str, app) -> bool:
    """書き直した spec を確かめて、通れば入れ替える。通らなければ前のまま動かし続ける"""
    from .runtime import Engine
    try:
        spec = parse_file(spec_path)
    except ParseError as e:
        print(f"読み直せません（前のまま動いています）\n  {spec_path}:{e.line}  {e.message}")
        return False
    errors = [f for f in check(spec) if f.is_error]
    if errors:
        print(f"読み直せません（{len(errors)}件。前のまま動いています）")
        for f in errors:
            path, line = spec.where(f.line)
            print(f"  {path}:{line}  {f.code}  {f.message}")
        return False
    app.reload(spec, Engine(spec, store=store))
    print("読み直しました")
    return True


def watch(spec_path: str, store: str, app, interval: float = 0.5) -> None:
    import time
    seen = watched_files(spec_path, app.spec)
    while True:
        time.sleep(interval)
        try:
            now = watched_files(spec_path, app.spec)
        except OSError:
            continue
        if now != seen:
            seen = now
            reload_once(spec_path, store, app)
            seen = watched_files(spec_path, app.spec)


def cmd_role(args) -> int:
    """最初の管理者を決める。2人目からは、画面で管理者が決める（spec の rule と who の通り）"""
    from .runtime import Engine, RuleError
    spec = _load_checked(args.spec)
    if spec is None:
        return 1
    store = args.data or (args.spec + ".data.jsonl")
    try:
        Engine(spec, store=store).set_role(args.name, args.role)
    except RuleError as e:
        print(e)
        return 1
    print(f"{args.name} を {args.role} にしました（データ: {store}）")
    return 0


def cmd_new(args) -> int:
    """ひな形から新しいアプリを作る（check も test も通る状態から始める）"""
    from pathlib import Path
    path = Path(args.name if args.name.endswith(".ponte") else args.name + ".ponte")
    if path.exists():
        print(f"もうあります: {path}（上書きしません）")
        return 1
    tpl = (Path(__file__).parent / "templates" / "start.ponte").read_text(encoding="utf-8")
    path.write_text(tpl, encoding="utf-8")
    print(f"作りました: {path}")
    print(f"  ponte run {path}     # 動かす")
    print(f"  ponte check {path}   # 書き換えたら確かめる")
    return 0


def cmd_guide(args) -> int:
    from .guide import do_guide, write_spec
    if args.spec:
        changed = write_spec(args.spec_path)
        print(f"{args.spec_path} の道具の表を{'書き直しました' if changed else '確かめました（変わりなし）'}")
        return 0
    if args.rules:
        from .guide import rules_guide
        print(rules_guide())
        return 0
    print(do_guide())
    return 0


def cmd_fill(args) -> int:
    from .fill import AnthropicHTTP, FileAI, fill_action, load_body
    spec = _load_checked(args.spec)
    if spec is None:
        return 1
    targets = [a for a in spec.decls("action")
               if (a.child("by") and a.child("by").text.strip() == "ai") and (not args.action or a.name == args.action)]
    if not targets:
        print("by ai の action がありません")
        return 1
    try:
        if args.ai.startswith("file:"):
            ai, label = FileAI(args.ai[5:]), f"用意した返事（{args.ai[5:]}）"
        else:
            ai, label = AnthropicHTTP(args.model, args.effort), args.model
    except RuntimeError as e:
        print(e)
        return 2
    bad = 0
    for a in targets:
        if load_body(spec, a) is not None and not args.again:
            print(f"  済み  {a.name}（書き直すなら --again）")
            continue
        print(f"  書かせています  {a.name} ...")
        try:
            r = fill_action(spec, a, ai, tries=args.tries, label=label)
        except RuntimeError as e:
            print(f"  止まりました  {a.name}: {e}")
            bad += 1
            continue
        for i, probs in enumerate(r.history, 1):
            print(f"    {i}回目: {'通過' if not probs else f'{len(probs)}件ダメ'}")
            for p in probs:
                print(f"      - {p}")
        if r.ok:
            print(f"  できました  {a.name}（{r.tries}回目で全部の example と never を通過）→ {r.path}")
        else:
            print(f"  できませんでした  {a.name}（{r.tries}回試した）")
            bad += 1
    return 1 if bad else 0


def cmd_fmt(args) -> int:
    from .fmt import FormatError, format_source
    rc = 0
    for path in args.spec:
        src = open(path, encoding="utf-8").read()
        try:
            new = format_source(src)
        except (FormatError, ParseError) as e:
            print(f"  {path}: 整形できません: {e}")
            rc = 2
            continue
        if new == src:
            print(f"  {path}: そのまま")
        elif args.check:
            print(f"  {path}: 整形が要ります")
            rc = max(rc, 1)
        else:
            open(path, "w", encoding="utf-8").write(new)
            print(f"  {path}: 整形しました")
    return rc


def cmd_build(args) -> int:
    from .build import build
    spec = _load_checked(args.spec)
    if spec is None:
        return 1
    out = args.out or (os.path.splitext(os.path.basename(args.spec))[0] + ".pyz")
    build(args.spec, out)
    print(f"1つのファイルにしました: {out}（python {out} で動く / python {out} check / python {out} test）")
    return 0


def cmd_user(args) -> int:
    """ログインする人を足す（ponte run --login 用）。合言葉は画面に出さずに聞く"""
    import getpass
    from .auth import Users
    users = Users(users_path(args.spec))
    if args.action == "list":
        for n in sorted(users.data):
            print(f"  {n}")
        return 0
    if not args.name:
        print("名前が要ります: ponte user add 仕様.ponte 名前")
        return 1
    if args.action == "remove":
        if users.data.pop(args.name, None) is None:
            print(f"{args.name} はいません")
            return 1
        users._save()
        print(f"{args.name} を消しました")
        return 0
    pw = os.environ.get("PONTE_PASSWORD") or getpass.getpass("合言葉（8文字以上）: ")
    try:
        users.add(args.name, pw)
    except ValueError as e:
        print(e)
        return 1
    print(f"{args.name} を登録しました（{users_path(args.spec)}）")
    return 0


def cmd_data(args) -> int:
    """保存したデータを書き出す（export）/ 追記の記録を今の中身1枚に詰める（compact）"""
    from .runtime import Engine
    spec = _load_checked(args.spec)
    if spec is None:
        return 1
    store = args.data or (args.spec + ".data.jsonl")
    if not os.path.exists(store):
        print(f"データがありません: {store}")
        return 1
    eng = Engine(spec, store=store)
    order = lambda b: int(b.id.split("-")[-1])
    if args.action == "export":
        things = {t: [{"id": b.id, **b.values} for b in sorted(eng.boxes[t].values(), key=order)] for t in eng.boxes}
        if args.csv:
            import csv
            os.makedirs(args.csv, exist_ok=True)
            for t, rows in things.items():
                cols = ["id"] + list(eng.fields.get(t, {}))
                with open(os.path.join(args.csv, f"{t}.csv"), "w", encoding="utf-8-sig", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
                    w.writeheader()
                    w.writerows(rows)
            print(f"{args.csv}/ に {len(things)}個の CSV を書きました（Excel でそのまま開けます）")
        else:
            print(json.dumps(things, ensure_ascii=False, indent=2))
        return 0
    # compact: 今の中身だけを、作った順に書き直す（古い記録は .bak に残す）
    before = sum(1 for _ in open(store, encoding="utf-8"))
    boxes = sorted((b for t in eng.boxes.values() for b in t.values()), key=order)
    tmp = store + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for b in boxes:
            f.write(json.dumps({"t": "create", "thing": b.thing, "id": b.id, "values": b.values}, ensure_ascii=False) + "\n")
    os.replace(store, store + ".bak")
    os.replace(tmp, store)
    print(f"{before}行 → {len(boxes)}行に詰めました（前のものは {store}.bak。動かしている間はしないでください）")
    return 0


def cmd_explain(args) -> int:
    from .errors import ERRORS, explain
    if not args.code:
        for c, title, _, _ in ERRORS:
            print(f"  {c}  {title}")
        return 0
    text = explain(args.code)
    if text is None:
        print(f"{args.code} というエラーはありません（一覧は ponte explain）")
        return 1
    print(text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ponte", description="Ponte — 人は決めて、AIが書いて、言語が守る（v0.3）")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="決めてないことを探す")
    c.add_argument("spec")
    c.add_argument("--publish", action="store_true", help="公開する時の検査")
    c.add_argument("--save-shape", action="store_true", help="通ったら thing の形を残す")
    c.add_argument("--json", action="store_true", help="結果を JSON で出す（エディタや AI のループ向け）")
    c.set_defaults(fn=cmd_check)
    t = sub.add_parser("test", help="rule の example を全部流す")
    t.add_argument("spec")
    t.add_argument("--strict", action="store_true", help="穴（example で確かめていない所）があれば失敗にする")
    t.set_defaults(fn=cmd_test)
    fl = sub.add_parser("fill", help="by ai の action の中身をAIに書かせる（example と never を通るまで）")
    fl.add_argument("spec")
    fl.add_argument("--action", help="この action だけ")
    fl.add_argument("--ai", default="anthropic", help="anthropic（ANTHROPIC_API_KEY が要る）か file:返事.md")
    fl.add_argument("--model", default="claude-opus-5")
    fl.add_argument("--effort", default="high")
    fl.add_argument("--tries", type=int, default=5)
    fl.add_argument("--again", action="store_true", help="もう中身があっても書き直す")
    fl.set_defaults(fn=cmd_fill)
    fm = sub.add_parser("fmt", help="誰が書いても同じ見た目に整える")
    fm.add_argument("spec", nargs="+")
    fm.add_argument("--check", action="store_true", help="書き換えず、整形が要るかだけ見る")
    fm.set_defaults(fn=cmd_fmt)
    bd = sub.add_parser("build", help="spec と中身と実行エンジンを1つの .pyz にまとめる")
    bd.add_argument("spec")
    bd.add_argument("-o", "--out")
    bd.set_defaults(fn=cmd_build)
    r = sub.add_parser("run", help="動かす（ブラウザで開く）")
    r.add_argument("spec")
    r.add_argument("--port", type=int, default=8000)
    r.add_argument("--host", default="127.0.0.1")
    r.add_argument("--data", help="データを残すファイル（既定は <spec>.data.jsonl）")
    r.add_argument("--login", action="store_true", help="名前と合言葉でログインする（登録は ponte user add）")
    r.add_argument("--signup", action="store_true", help="--login に加えて、画面から誰でも登録できる")
    r.add_argument("--reload", action="store_true", help="spec を書き直したら読み直して、画面も読み直す（作っている間に）")
    r.set_defaults(fn=cmd_run)
    us = sub.add_parser("user", help="ログインする人（例: user add spec/lend.ponte taro）")
    us.add_argument("action", choices=["add", "remove", "list"])
    us.add_argument("spec")
    us.add_argument("name", nargs="?")
    us.set_defaults(fn=cmd_user)
    nw = sub.add_parser("new", help="ひな形から新しいアプリを作る")
    nw.add_argument("name")
    nw.set_defaults(fn=cmd_new)
    g = sub.add_parser("guide", help="AIに渡す書き方の説明を出す（実装から作る）")
    g.add_argument("--spec", action="store_true", help="仕様書 10章の道具の表を書き直す")
    g.add_argument("--rules", action="store_true", help="rule の書き方（when / do / 値）を出す")
    g.add_argument("--spec-path", default="docs/言語仕様_v0.3.md")
    g.set_defaults(fn=cmd_guide)
    ro = sub.add_parser("role", help="最初の管理者を決める（例: role spec/lend.ponte taro admin）")
    ro.add_argument("spec")
    ro.add_argument("name")
    ro.add_argument("role")
    ro.add_argument("--data", help="データのファイル（既定は <spec>.data.jsonl）")
    ro.set_defaults(fn=cmd_role)
    da = sub.add_parser("data", help="保存したデータを書き出す（export）・詰める（compact）")
    da.add_argument("action", choices=["export", "compact"])
    da.add_argument("spec")
    da.add_argument("--data", help="データのファイル（既定は <spec>.data.jsonl）")
    da.add_argument("--csv", metavar="DIR", help="export を thing ごとの CSV にする")
    da.set_defaults(fn=cmd_data)
    ex = sub.add_parser("explain", help="エラーの意味と直し方（例: explain E32。無しなら一覧）")
    ex.add_argument("code", nargs="?")
    ex.set_defaults(fn=cmd_explain)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
