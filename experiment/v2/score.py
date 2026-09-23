"""比較実験 v2 の採点。runs/ を読んで EXPERIMENT.md を書く。

  python experiment/v2/score.py

A: runs/A{i}/system.py            （AIが Python で全部書いたもの）
B: runs/B{i}/reply.md            （AIの1回目の返事。do と shape）
   runs/B{i}/reply{k}.md         （言語のループで問題を返した後の返事。あれば）
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import harness  # noqa: E402
from ponte.fill import extract_code, verify  # noqa: E402
from ponte.parser import parse_file  # noqa: E402

N_TESTS = len(harness.TESTS)


def questions(text: str) -> list[str]:
    return [l.strip() for l in text.splitlines() if re.match(r"^\s*#?\s*Q[:：]", l)]


def score_a(d: Path) -> dict:
    p = d / "system.py"
    if not p.exists():
        return {"run": d.name, "missing": True}
    src = p.read_text(encoding="utf-8")
    r = {"run": d.name, "lines": len([l for l in src.splitlines() if l.strip()]), "questions": questions(src), "code": src}
    try:
        res = harness.run(harness.load_a(p))
        r["ran"] = True
    except Exception as e:     # noqa: BLE001  読み込みで落ちた
        res = [(n, False, ex, f"読み込めない: {e}") for n, _, ex in harness.TESTS]
        r["ran"] = False
    r["results"] = res
    return r


def score_b_reply(text: str) -> dict:
    code = extract_code(text)
    spec = parse_file(str(harness.SPEC))
    a = spec.find("action", "ExtractDeadline")
    if code is None:
        return {"ran": False, "problems": ["コードブロックが無い"], "results": [(n, False, ex, "コード無し") for n, _, ex in harness.TESTS], "code": ""}
    v = verify(spec, a, code)
    try:
        res = harness.run(harness.load_b(code))
        ran = True
    except Exception as e:     # noqa: BLE001  読めない do
        res = [(n, False, ex, f"読み込めない: {e}") for n, _, ex in harness.TESTS]
        ran = False
    return {"ran": ran, "problems": v.problems, "results": res, "code": code}


def score_b(d: Path) -> dict:
    p = d / "reply.md"
    if not p.exists():
        return {"run": d.name, "missing": True}
    first = p.read_text(encoding="utf-8")
    r = {"run": d.name, "questions": questions(first.split("```")[0])}
    r["first"] = score_b_reply(first)
    r["lines"] = len([l for l in r["first"]["code"].splitlines() if l.strip()])
    later = sorted(d.glob("reply[0-9]*.md"), key=lambda x: int(re.sub(r"\D", "", x.name)))
    r["rounds"] = 1 + len(later)
    r["final"] = score_b_reply(later[-1].read_text(encoding="utf-8")) if later else r["first"]
    return r


def fails(res):
    return [n for n, ok, _, _ in res if not ok]


def examples_ok(res):
    return all(ok for _, ok, ex, _ in res if ex)


def variation(codes: list[str]) -> float | None:
    codes = [c.splitlines() for c in codes if c]
    if len(codes) < 2:
        return None
    total, n = 0, 0
    for i in range(len(codes)):
        for j in range(i + 1, len(codes)):
            total += sum(1 for l in difflib.unified_diff(codes[i], codes[j], lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---"))
            n += 1
    return total / n


def avg(xs):
    return sum(xs) / len(xs) if xs else 0


def section(runs: Path, title: str) -> tuple[list[str], dict]:
    A = [x for x in (score_a(d) for d in sorted(runs.glob("A*"))) if not x.get("missing")]
    B = [x for x in (score_b(d) for d in sorted(runs.glob("B*"))) if not x.get("missing")]
    L = [f"## {title}", "", f"### (A) 日本語で頼む（{len(A)}回）", "",
         "| run | 動いた | 仕様の例を通過 | バグ数 | 推測で埋めた所（Q:） | AIが書いた行数 |", "|---|---|---|---|---|---|"]
    for r in A:
        L.append(f"| {r['run']} | {'✓' if r['ran'] else '✗'} | {'✓' if examples_ok(r['results']) else '✗'} | {len(fails(r['results']))} | {len(r['questions'])} | {r['lines']} |")
    L += ["", f"### (B) この言語で頼む（{len(B)}回）", "",
          "| run | 動いた | 仕様の例を通過 | バグ数（1回目） | 推測で埋めた所（Q:） | 言語のループの回数 | バグ数（ループ後） | AIが書いた行数 |", "|---|---|---|---|---|---|---|---|"]
    for r in B:
        L.append(f"| {r['run']} | {'✓' if r['first']['ran'] else '✗'} | {'✓' if examples_ok(r['first']['results']) else '✗'} | {len(fails(r['first']['results']))} | {len(r['questions'])} | {r['rounds']} | {len(fails(r['final']['results']))} | {r['lines']} |")
    a_b = [len(fails(r["results"])) for r in A]
    b1 = [len(fails(r["first"]["results"])) for r in B]
    bf = [len(fails(r["final"]["results"])) for r in B]
    va, vb = variation([r["code"] for r in A]) or 0, variation([r["final"]["code"] for r in B]) or 0
    la, lb = avg([r["lines"] for r in A]), avg([r["lines"] for r in B])
    sm = {
        "all_pass": (sum(x == 0 for x in a_b), sum(x == 0 for x in b1), sum(x == 0 for x in bf), len(A), len(B)),
        "examples": (sum(examples_ok(r["results"]) for r in A), sum(examples_ok(r["first"]["results"]) for r in B), sum(examples_ok(r["final"]["results"]) for r in B)),
        "bugs": (avg(a_b), avg(b1), avg(bf)),
        "q": (sum(len(r["questions"]) for r in A), sum(len(r["questions"]) for r in B)),
        "lines": (la, lb),
        "var": (va, vb, va / la if la else 0, vb / lb if lb else 0),
    }
    L += ["", "### どの要件で間違えたか（落ちた回数）", "", "| 要件 | (A) | (B) 1回目 | (B) ループ後 |", "|---|---|---|---|"]
    for i, (name, _, _) in enumerate(harness.TESTS):
        L.append(f"| {name} | {sum(1 for r in A if not r['results'][i][1])} | {sum(1 for r in B if not r['first']['results'][i][1])} | {sum(1 for r in B if not r['final']['results'][i][1])} |")
    L += ["", "### 失敗の中身", ""]
    for r in A:
        L += [f"- {r['run']}: {n} — {m}" for n, ok, _, m in r["results"] if not ok]
    for r in B:
        L += [f"- {r['run']}（1回目）: {n} — {m}" for n, ok, _, m in r["first"]["results"] if not ok]
        if r["rounds"] > 1:
            L.append(f"- {r['run']}: 言語が返した問題 → " + " / ".join(r["first"]["problems"]))
    qs = [f"- {r['run']}: {q.lstrip('#').strip()}" for r in A + B for q in r["questions"]]
    if qs:
        L += ["", "### 推測で埋めた所（AIが書いた Q:）", ""] + qs
    return L + [""], sm


def main():
    rounds = [("runs", "1回目の実験（そのままの条件）"), ("runs2", "2回目の実験（粗を直した後。日本語の要件も同じだけはっきり書いた）"),
              ("runs3", "3回目の実験（別のモデル Haiku で。条件は2回目と同じ。各6回・1回ごとに別のエージェント）")]
    parts, sums = [], []
    for d, t in rounds:
        if (HERE / d).exists():
            L, sm = section(HERE / d, t)
            parts.append(L)
            sums.append((t, sm))
    head = ["# EXPERIMENT v2 — 自然文 vs この言語（就活Hub）", "",
            "同じ要件を2通りで渡して、AIに各5回ずつ実装させた。採点は AI に見せていない同じ14個のテスト（`experiment/v2/harness.py`）。", "",
            "| | (A) 日本語で頼む | (B) この言語で頼む |", "|---|---|---|",
            "| AIが書くもの | 全部（Python 1ファイル） | action ExtractDeadline の中身（do と shape）だけ。残りは spec から言語が決まった通りに動かす |",
            "| AI | Claude のサブエージェント（Sonnet）。渡したプロンプト1つだけ読み、コードは動かさない | 同じ |",
            "| 言語のループ | 無し | 機械が確かめてダメなら、問題をそのまま返して書き直させる |", "",
            "## まとめ", "", "| 項目 | " + " | ".join(f"{t[:6]} (A)" + f" | {t[:6]} (B)1回目 | {t[:6]} (B)ループ後" for t, _ in sums) + " |",
            "|---" * (1 + 3 * len(sums)) + "|"]
    def row(label, f):
        return f"| {label} | " + " | ".join(f(sm) for _, sm in sums) + " |"
    head += [
        row("14テスト全部通った", lambda m: f"{m['all_pass'][0]}/{m['all_pass'][3]} | {m['all_pass'][1]}/{m['all_pass'][4]} | {m['all_pass'][2]}/{m['all_pass'][4]}"),
        row("仕様の例を全部通った", lambda m: f"{m['examples'][0]}/{m['all_pass'][3]} | {m['examples'][1]}/{m['all_pass'][4]} | {m['examples'][2]}/{m['all_pass'][4]}"),
        row("バグ数の平均", lambda m: f"{m['bugs'][0]:.1f} | {m['bugs'][1]:.1f} | {m['bugs'][2]:.1f}"),
        row("推測で埋めた所の合計", lambda m: f"{m['q'][0]} | {m['q'][1]} | —"),
        row("AIが書いた行数の平均", lambda m: f"{m['lines'][0]:.0f} | {m['lines'][1]:.0f} | —"),
        row("ブレ（差分行数の平均 / 書いた1行あたり）", lambda m: f"{m['var'][0]:.0f} / {m['var'][2]:.2f} | — | {m['var'][1]:.0f} / {m['var'][3]:.2f}"),
        ""]
    notes = (HERE / "notes.md").read_text(encoding="utf-8") if (HERE / "notes.md").exists() else ""
    out = head + [l for p in parts for l in p] + [notes]
    (HERE.parent.parent / "EXPERIMENT.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(head))


if __name__ == "__main__":
    main()
