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
from lang.fill import extract_code, verify  # noqa: E402
from lang.parser import parse_file  # noqa: E402

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


def main():
    A = [score_a(d) for d in sorted((HERE / "runs").glob("A*"))]
    B = [score_b(d) for d in sorted((HERE / "runs").glob("B*"))]
    A = [x for x in A if not x.get("missing")]
    B = [x for x in B if not x.get("missing")]
    L = ["# EXPERIMENT v2 — 自然文 vs この言語（就活Hub）", ""]
    L += ["## やったこと", "",
          "同じ要件を2通りで渡して、AIに各5回ずつ実装させた。採点は AI に見せていない同じ14個のテスト。", "",
          "| | (A) 日本語で頼む | (B) この言語で頼む |", "|---|---|---|",
          "| AIに渡したもの | 日本語の要件と、Python の窓口（`prompts/A_japanese.md`） | action の契約と、中身の書き方（`prompts/B_lang.md`。`python -m lang fill` が送るものと同じ） |",
          "| AIが書くもの | 全部（Python 1ファイル） | action ExtractDeadline の中身（do と shape）だけ。残りは spec から言語が決まった通りに動かす |",
          "| 採点 | `harness.py` の14テスト | 同じ14テスト（spec + AIの中身を同じ窓口に揃えて当てる） |",
          "| AI | Claude のサブエージェント。モデルは両方 Sonnet に固定。ファイルは渡したプロンプト1つだけ読ませ、コードは動かさせない | 同じ |", ""]
    L += ["## 結果", "", f"### (A) 日本語で頼む（{len(A)}回）", "",
          "| run | 動いた | 仕様の例を通過 | バグ数（落ちたテスト） | 聞き返し | AIが書いた行数 |", "|---|---|---|---|---|---|"]
    for r in A:
        L.append(f"| {r['run']} | {'✓' if r['ran'] else '✗'} | {'✓' if examples_ok(r['results']) else '✗'} | {len(fails(r['results']))} | {len(r['questions'])} | {r['lines']} |")
    L += ["", f"### (B) この言語で頼む（{len(B)}回）", "",
          "| run | 動いた | 仕様の例を通過 | バグ数（1回目） | 聞き返し | 言語のループの回数 | バグ数（ループ後） | AIが書いた行数 |", "|---|---|---|---|---|---|---|---|"]
    for r in B:
        L.append(f"| {r['run']} | {'✓' if r['first']['ran'] else '✗'} | {'✓' if examples_ok(r['first']['results']) else '✗'} | {len(fails(r['first']['results']))} | {len(r['questions'])} | {r['rounds']} | {len(fails(r['final']['results']))} | {r['lines']} |")
    # まとめ
    def avg(xs):
        return sum(xs) / len(xs) if xs else 0
    a_b = [len(fails(r["results"])) for r in A]
    b1 = [len(fails(r["first"]["results"])) for r in B]
    bf = [len(fails(r["final"]["results"])) for r in B]
    L += ["", "## まとめ", "",
          "| 項目 | (A) 日本語 | (B) この言語（1回目） | (B) この言語（ループ後） |", "|---|---|---|---|",
          f"| 動いた回数 | {sum(r['ran'] for r in A)}/{len(A)} | {sum(r['first']['ran'] for r in B)}/{len(B)} | {sum(r['final']['ran'] for r in B)}/{len(B)} |",
          f"| 仕様の例を全部通った回数 | {sum(examples_ok(r['results']) for r in A)}/{len(A)} | {sum(examples_ok(r['first']['results']) for r in B)}/{len(B)} | {sum(examples_ok(r['final']['results']) for r in B)}/{len(B)} |",
          f"| 14テスト全部通った回数 | {sum(x == 0 for x in a_b)}/{len(A)} | {sum(x == 0 for x in b1)}/{len(B)} | {sum(x == 0 for x in bf)}/{len(B)} |",
          f"| バグ数の合計（平均） | {sum(a_b)}（{avg(a_b):.1f}） | {sum(b1)}（{avg(b1):.1f}） | {sum(bf)}（{avg(bf):.1f}） |",
          f"| 聞き返しの合計 | {sum(len(r['questions']) for r in A)} | {sum(len(r['questions']) for r in B)} | — |",
          f"| AIが書いた行数の平均 | {avg([r['lines'] for r in A]):.0f} | {avg([r['lines'] for r in B]):.0f} | — |",
          f"| 5回のブレ（run 同士の差分行数の平均） | {variation([r['code'] for r in A]) or 0:.0f} | {variation([r['first']['code'] for r in B]) or 0:.0f} | {variation([r['final']['code'] for r in B]) or 0:.0f} |", ""]
    # どのテストで落ちたか
    L += ["## どの要件で間違えたか（落ちた回数）", "", "| 要件 | (A) | (B) 1回目 | (B) ループ後 |", "|---|---|---|---|"]
    for i, (name, _, _) in enumerate(harness.TESTS):
        ca = sum(1 for r in A if not r["results"][i][1])
        c1 = sum(1 for r in B if not r["first"]["results"][i][1])
        cf = sum(1 for r in B if not r["final"]["results"][i][1])
        L.append(f"| {name} | {ca} | {c1} | {cf} |")
    L += ["", "## 聞き返し（AIが書いた Q:）", ""]
    for r in A + B:
        for q in r["questions"]:
            L.append(f"- {r['run']}: {q.lstrip('#').strip()}")
    L += ["", "## 失敗の中身", ""]
    for r in A:
        for n, ok, _, msg in r["results"]:
            if not ok:
                L.append(f"- {r['run']}: {n} — {msg}")
    for r in B:
        for n, ok, _, msg in r["first"]["results"]:
            if not ok:
                L.append(f"- {r['run']}（1回目）: {n} — {msg}")
        if r["rounds"] > 1:
            L.append(f"- {r['run']}: 言語が返した問題（1回目）: " + " / ".join(r["first"]["problems"]))
    (HERE.parent.parent / "EXPERIMENT.md").write_text("\n".join(L) + "\n__NOTES__\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
