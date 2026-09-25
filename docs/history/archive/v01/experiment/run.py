"""フェーズ3：同じ要件を (A) 日本語 / (B) この言語 で AI に渡して、各5回実装させる。

  python experiment/run.py                 # ANTHROPIC_API_KEY があれば本番。無ければ止まる
  python experiment/run.py --dummy         # API を呼ばずにダミー結果を置く（手順の確認用）
  python experiment/run.py --runs 5 --model claude-opus-5 --effort high

結果: experiment/results/<A|B>/run<i>/response.md, hub.go, meta.json
モデルと effort は固定する（Opus 5 系は temperature が無いので、effort と thinking の設定を固定して代わりにする）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
PROMPTS = HERE / "prompts"
RESULTS = HERE / "results"

SYSTEM = "あなたは Go のプログラマーです。渡された要件を実装します。"


def build_prompt(condition: str) -> str:
    body = (PROMPTS / ("A_japanese.md" if condition == "A" else "B_lang.md")).read_text(encoding="utf-8")
    common = (PROMPTS / "common.md").read_text(encoding="utf-8")
    return body + "\n\n" + common


def extract_go(text: str) -> str | None:
    m = re.search(r"```go\n(.*?)```", text, re.S)
    return m.group(1) if m else None


def call_model(client, model: str, effort: str, prompt: str) -> tuple[str, dict]:
    # 長い出力になるのでストリーミングで受ける。thinking は省略（adaptive）。
    with client.messages.stream(
        model=model,
        max_tokens=32000,
        system=SYSTEM,
        output_config={"effort": effort},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        msg = stream.get_final_message()
    text = "".join(b.text for b in msg.content if b.type == "text")
    meta = {
        "model": msg.model,
        "stop_reason": msg.stop_reason,
        "input_tokens": msg.usage.input_tokens,
        "output_tokens": msg.usage.output_tokens,
    }
    return text, meta


def write_result(condition: str, i: int, text: str, meta: dict) -> None:
    d = RESULTS / condition / f"run{i}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "response.md").write_text(text, encoding="utf-8")
    code = extract_go(text)
    if code is not None:
        (d / "hub.go").write_text(code, encoding="utf-8")
    elif (d / "hub.go").exists():
        (d / "hub.go").unlink()
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--model", default="claude-opus-5")
    p.add_argument("--effort", default="high")
    p.add_argument("--dummy", action="store_true", help="API を呼ばずダミー結果を置く")
    p.add_argument("--conditions", default="A,B")
    args = p.parse_args()

    conditions = args.conditions.split(",")
    if args.dummy:
        for c in conditions:
            for i in range(1, args.runs + 1):
                write_result(c, i, "（ダミー）API キーが無いので未実行。\n", {"dummy": True, "model": args.model, "effort": args.effort})
        print(f"ダミー結果を置きました: {RESULTS}")
        return 0

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY がありません。--dummy で手順だけ通せます", file=sys.stderr)
        return 2
    import anthropic  # 実行時だけ読み込む
    client = anthropic.Anthropic()
    for c in conditions:
        prompt = build_prompt(c)
        for i in range(1, args.runs + 1):
            print(f"[{c} run{i}] {args.model} effort={args.effort} ...", flush=True)
            text, meta = call_model(client, args.model, args.effort, prompt)
            meta.update({"condition": c, "run": i, "effort": args.effort})
            write_result(c, i, text, meta)
            print(f"[{c} run{i}] stop={meta['stop_reason']} out={meta['output_tokens']}tok code={'yes' if extract_go(text) else 'no'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
