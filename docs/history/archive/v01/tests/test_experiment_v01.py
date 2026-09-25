"""フェーズ3の採点パイプラインの検算。"""
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path("experiment")))
import score  # noqa: E402
from run import build_prompt, extract_go  # noqa: E402

needs_go = pytest.mark.skipif(shutil.which("go") is None, reason="go が無い")


@needs_go
def test_reference_passes_harness():
    r = score.run_go(Path("experiment/reference/hub.go"))
    assert r["compiled"] and r["failed"] == [], r


@needs_go
def test_broken_code_counts_bugs(tmp_path):
    src = Path("experiment/reference/hub.go").read_text(encoding="utf-8")
    broken = src.replace('case "passed":\n\t\treturn "blue"', 'case "passed":\n\t\treturn "green"')
    p = tmp_path / "hub.go"
    p.write_text(broken, encoding="utf-8")
    r = score.run_go(p)
    assert r["compiled"] and r["failed"] == ["TestMatchColor"], r


def test_prompts_and_extraction():
    a, b = build_prompt("A"), build_prompt("B")
    assert "共通の指示" in a and "共通の指示" in b
    assert "entity Application" in b and "entity Application" not in a
    assert extract_go("x\n```go\npackage hub\n```\n") == "package hub\n"
    assert extract_go("Q: 何？") is None
    assert score.count_questions("Q: a\nQ: b\n", has_code=False) == 2
    assert score.count_questions("Q: a", has_code=True) == 0


def test_score_dummy_results_do_not_crash():
    rows = {"A": {"runs": [], "variation": None}, "B": {"runs": [], "variation": None}}
    assert "未実行" in score.render(rows)
