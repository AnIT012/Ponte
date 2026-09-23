"""AIへの説明（lang guide）と仕様書 10章は、実装から作る。ずれたらここで落ちる。"""
import pytest

from lang.body import TOOLS, TOOLS_HINT, BodyError, body_of
from lang.guide import do_guide, spec_block
from lang.parser import parse

SHAPES = """
shape D
  n digits 1..5

shape M
  month digits 1..2
  "/"
  day digits 1..2
"""


def run(expr, t):
    src = f"action A\n  in t text\n  out text\n  example \"x\" -> x\n  else skip\n  do\n    answer = {expr}\n{SHAPES}"
    spec = parse(src)
    a = spec.find("action", "A")
    b = body_of(a, a.child("do"), {s.name: s for s in spec.decls("shape")})
    return b.run({"t": t})


@pytest.mark.parametrize("tool", [t for t in TOOLS if t[3]], ids=lambda t: t[1])
def test_every_tool_example_really_works(tool):
    _, _, _, expr, inp, want = tool
    assert run(expr, inp) == want


@pytest.mark.parametrize("expr", ["sum of t", "round t", "weekday of t", "take 3 of t", "t contains \"a\""])
def test_tools_listed_as_not_yet_are_errors(expr):
    with pytest.raises(BodyError):
        run(expr, "a")


def test_spec_chapter_10_is_generated_from_the_code():
    text = open("docs/言語仕様_v0.3.md", encoding="utf-8").read()
    assert spec_block() in text, "仕様書の道具の表が実装とずれています。python -m lang guide --spec で書き直す"


def test_guide_and_hint_list_every_tool():
    g = do_guide()
    for _, form, *_ in TOOLS:
        assert form in g and form in TOOLS_HINT
    assert "never depend on width" in g and "FindMonthDay" in g


def test_fill_prompt_uses_the_generated_guide():
    from lang.fill import first_prompt as build_prompt
    from lang.parser import parse_file
    spec = parse_file("spec/hub_app.lang")
    assert do_guide() in build_prompt(spec, spec.find("action", "ExtractDeadline"))
