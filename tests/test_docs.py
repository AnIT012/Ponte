"""ドキュメントに書いたコードと出力が、本当にその通りになるか。"""
import re

from lang.checker import check
from lang.examples import holes, run_examples
from lang.parser import parse, parse_file

DOC = open("docs/入門.md", encoding="utf-8").read()
BLOCKS = re.findall(r"```\n(.*?)```", DOC, re.S)


def code(i):
    return BLOCKS[i]


def findings(src):
    return [f"todo.lang:{f.line}  {f.code}  {f.message}" for f in check(parse(src)) if f.is_error]


def test_tutorial_outputs_are_real():
    step1 = code(0)
    step2 = step1 + "\n" + code(2)
    step3 = step2 + "\n" + code(3)
    for src in (step1, step3):
        for line in findings(src):
            assert line in DOC, line
    fixed = step3.replace("move this to finished", "move this to done")
    assert findings(fixed) == []
    s = parse(fixed)
    for h in holes(s, run_examples(s)):
        assert f"todo.lang:{h.line}  {h.message}" in DOC, h.message
    step5 = fixed + "\n" + [b for b in BLOCKS if "due within 1 days" in b and "rule Remind" in b][0]
    for line in findings(step5):
        assert line in DOC, line


def test_finished_tutorial_app_has_no_holes():
    s = parse_file("spec/todo.lang")
    assert [f for f in check(s) if f.is_error] == []
    res = run_examples(s)
    assert all(r.ok for r in res) and holes(s, res) == []


def test_every_sample_app_passes_check_and_test():
    import glob
    for p in sorted(glob.glob("spec/*.lang")):
        if p.endswith("spec/hub.lang"):          # 仕様書の付録そのまま（tbd で止まるのが正しい）
            continue
        s = parse_file(p)
        assert [f for f in check(s) if f.is_error] == [], p
        assert all(r.ok for r in run_examples(s)), p
