"""フェーズ3の採点。results/ を読んで EXPERIMENT.md の表を作る。

数えるもの（1 run ごと）:
  動いたか        : hub.go があり go vet が通り、ハーネスがコンパイルできる
  example を通ったか: TestSpecExampleRemind と TestExtractDeadlineExamples が通る
  バグの数        : 落ちたテストの数（コンパイルできなければ全テスト数）
  聞き返した回数  : コードを出さず "Q:" で始まる行の数（コード付きなら 0）
5 run のブレ     : run 同士の hub.go の差分行数（追加＋削除）の平均
"""
from __future__ import annotations

import difflib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
RESULTS = HERE / "results"
HARNESS = HERE / "harness_test.go"
TEST_NAMES = [m.group(1) for m in re.finditer(r"^func (Test\w+)\(", HARNESS.read_text(encoding="utf-8"), re.M)]
EXAMPLE_TESTS = {"TestSpecExampleRemind", "TestExtractDeadlineExamples"}


def run_go(hub_go: Path) -> dict:
    """1 run 分を go test -race にかける。"""
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        (dd / "go.mod").write_text("module hub\n\ngo 1.22\n")
        shutil.copy(hub_go, dd / "hub.go")
        shutil.copy(HARNESS, dd / "harness_test.go")
        vet = subprocess.run(["go", "vet", "./..."], cwd=dd, capture_output=True, text=True)
        if vet.returncode != 0:
            return {"compiled": False, "failed": list(TEST_NAMES), "log": vet.stderr[-2000:]}
        r = subprocess.run(["go", "test", "-race", "-json", "./..."], cwd=dd, capture_output=True, text=True, timeout=300)
        failed = []
        for line in r.stdout.splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("Action") == "fail" and ev.get("Test"):
                failed.append(ev["Test"])
        if r.returncode != 0 and not failed:
            return {"compiled": False, "failed": list(TEST_NAMES), "log": (r.stdout + r.stderr)[-2000:]}
        return {"compiled": True, "failed": failed, "log": ""}


def count_questions(response: str, has_code: bool) -> int:
    if has_code:
        return 0
    return len(re.findall(r"^\s*Q[:：]", response, re.M)) or (1 if re.search(r"[?？]", response) else 0)


def score_run(d: Path) -> dict:
    resp = (d / "response.md").read_text(encoding="utf-8") if (d / "response.md").exists() else ""
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8")) if (d / "meta.json").exists() else {}
    hub = d / "hub.go"
    out = {"run": d.name, "dummy": bool(meta.get("dummy")), "has_code": hub.exists()}
    out["questions"] = count_questions(resp, hub.exists())
    if out["dummy"]:
        return out
    if not hub.exists():
        out.update(compiled=False, failed=list(TEST_NAMES), log="コード無し")
    else:
        out.update(run_go(hub))
    out["bugs"] = len(out["failed"])
    out["examples_pass"] = out["compiled"] and not (EXAMPLE_TESTS & set(out["failed"]))
    return out


def variation(dirs: list[Path]) -> float | None:
    codes = [(d / "hub.go").read_text(encoding="utf-8").splitlines() for d in dirs if (d / "hub.go").exists()]
    if len(codes) < 2:
        return None
    total, n = 0, 0
    for i in range(len(codes)):
        for j in range(i + 1, len(codes)):
            diff = [l for l in difflib.unified_diff(codes[i], codes[j], lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
            total += len(diff)
            n += 1
    return total / n


def fmt(v, dummy: bool) -> str:
    if dummy:
        return "—"
    if isinstance(v, bool):
        return "✓" if v else "✗"
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)


def main() -> int:
    rows = {}
    for c in ("A", "B"):
        dirs = sorted((RESULTS / c).glob("run*")) if (RESULTS / c).exists() else []
        rows[c] = {"runs": [score_run(d) for d in dirs], "variation": variation(dirs)}
    report = render(rows)
    (HERE.parent / "EXPERIMENT.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


def render(rows: dict) -> str:
    any_real = any(not r["dummy"] for c in rows.values() for r in c["runs"])
    L = ["# EXPERIMENT — 自然文 vs この言語（就活Hub：メール→締切→通知）", ""]
    if not any_real:
        L += ["> **まだ本番は未実行**（ANTHROPIC_API_KEY 未設定）。下の表はダミーで、手順が通ることだけ確認済み。",
              "> `ANTHROPIC_API_KEY=... python experiment/run.py && python experiment/score.py` で本番の数字に置き換わる。", ""]
    L += ["## 条件", "",
          "| | (A) 日本語の自然文 | (B) この言語 |", "|---|---|---|",
          "| 入力 | `experiment/prompts/A_japanese.md` | `experiment/prompts/B_lang.md`（`spec/hub_ready.spec` をそのまま） |",
          "| 共通 | `experiment/prompts/common.md`（テストの窓口・「分からなければ質問だけ返す」） | 同じ |",
          "| 採点 | `experiment/harness_test.go`（10テスト、AIには見せない） | 同じ |",
          "| モデル | run.py の `--model`（既定 claude-opus-5）、`--effort` 固定 | 同じ |", ""]
    L += ["## 結果（1 run = 1回の実装）", ""]
    for c, label in (("A", "日本語"), ("B", "この言語")):
        L += [f"### ({c}) {label}", "",
              "| run | 動いた | example 通過 | バグ数 | 聞き返し |", "|---|---|---|---|---|"]
        for r in rows[c]["runs"]:
            d = r["dummy"]
            L.append(f"| {r['run']} | {fmt(r.get('compiled'), d)} | {fmt(r.get('examples_pass'), d)} | {fmt(r.get('bugs'), d)} | {fmt(r['questions'], d) if not d else '—'} |")
        v = rows[c]["variation"]
        L += ["", f"5回のブレ（run 同士の差分行数の平均）: **{fmt(v, v is None)}**", ""]
    L += ["## まとめ（本番の数字が出たら書く）", "",
          "| 項目 | (A) 日本語 | (B) この言語 | 勝ち |", "|---|---|---|---|"]
    for key, label in (("compiled", "動いた回数"), ("examples_pass", "example 通過回数"), ("bugs", "バグ数の合計"), ("questions", "聞き返し回数の合計")):
        vals = []
        for c in ("A", "B"):
            rs = [r for r in rows[c]["runs"] if not r["dummy"]]
            if not rs:
                vals.append(None)
            elif key in ("compiled", "examples_pass"):
                vals.append(sum(1 for r in rs if r.get(key)))
            else:
                vals.append(sum(r.get(key, 0) for r in rs))
        if vals[0] is None or vals[1] is None:
            win = "—"
        else:
            better_high = key in ("compiled", "examples_pass")
            if vals[0] == vals[1]:
                win = "引き分け"
            else:
                win = "A" if (vals[0] > vals[1]) == better_high else "B"
        L.append(f"| {label} | {fmt(vals[0], vals[0] is None)} | {fmt(vals[1], vals[1] is None)} | {win} |")
    va, vb = rows["A"]["variation"], rows["B"]["variation"]
    if va is None or vb is None:
        win = "—"
    else:
        win = "引き分け" if va == vb else ("A" if va < vb else "B")
    L.append(f"| 5回のブレ（差分行数の平均） | {fmt(va, va is None)} | {fmt(vb, vb is None)} | {win} |")
    L += ["", "## 正直な注記", "",
          "- 「聞き返し」は、コードを出さずに質問だけ返した run の `Q:` 行の数。コードも質問も両方出した場合は 0 と数える（採点を機械的にするため）。",
          "- バグ数はハーネスの落ちたテスト数。コンパイルできなければ全テスト（10）を落ちた扱い。",
          "- ブレはコードの見た目の差分なので、同じ動きでも書き方が違えば大きく出る。動作の安定は「バグ数」の分散で見る。",
          "- (B) の方が要件の情報量が多い（example・never・else・how が明示されている）ので、公平な比較というより「言語で書くとどこまで揃うか」の測定。この点はこの言語に有利。",
          "- 逆に、(B) は読み方の説明を付けているとはいえ AI が初見の記法で、(A) は慣れた自然文。この点はこの言語に不利。",
          ""]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
