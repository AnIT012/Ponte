"""AIへの説明（ponte guide）と仕様書 10章は、実装から作る。ずれたらここで落ちる。"""
import pytest

from ponte.body import TOOLS, TOOLS_HINT, BodyError, body_of
from ponte.guide import do_guide, spec_block
from ponte.parser import parse

SHAPES = """
shape D
  n digits 1..5

shape M
  month digits 1..2
  "/"
  day digits 1..2

shape Y
  year digits 4
  "年"
  month digits 1..2
  "月"
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


@pytest.mark.parametrize("expr", ["time of t", "each t", "group by t"])
def test_tools_listed_as_not_yet_are_errors(expr):
    with pytest.raises(BodyError):
        run(expr, "a")


def test_spec_chapter_10_is_generated_from_the_code():
    text = open("docs/言語仕様_v0.3.md", encoding="utf-8").read()
    assert spec_block() in text, "仕様書の道具の表が実装とずれています。python -m ponte guide --spec で書き直す"


def test_guide_and_hint_list_every_tool():
    g = do_guide()
    for _, form, *_ in TOOLS:
        assert form in g and form in TOOLS_HINT
    assert "never depend on width" in g and "FindMonthDay" in g


def test_fill_prompt_uses_the_generated_guide():
    from ponte.fill import first_prompt as build_prompt
    from ponte.parser import parse_file
    spec = parse_file("spec/hub_app.ponte")
    assert do_guide() in build_prompt(spec, spec.find("action", "ExtractDeadline"))


def test_contains_answer_is_split_with_match():
    src = """action A
  in t text
  out found text | missing
  example "x" -> missing
  else skip
  do
    has[yes | no] = match t contains "締切"
                      yes -> yes
                      no  -> no
    answer = match has
               yes -> found t
               no  -> missing
"""
    spec = parse(src)
    a = spec.find("action", "A")
    b = body_of(a, a.child("do"), {})
    assert str(b.run({"t": "締切は明日"})) == "found 締切は明日" and str(b.run({"t": "こんにちは"})) == "missing"


def test_rule_forms_examples_pass_the_checker():
    import re
    from ponte.checker import DO_FORMS as CHECKED_DO, _VALUE, is_event
    from ponte.forms import DO_FORMS, VALUE_FORMS, WHEN_FORMS
    for rx, form, _, ex, works in WHEN_FORMS:
        assert re.fullmatch(rx, ex), form
        assert is_event(ex) == works, form          # 起きないものは check が通さない
    for rx, form, _, ex in DO_FORMS:
        assert re.fullmatch(rx, ex), form
        assert rx in CHECKED_DO or form.startswith("action名"), form
    for rx, form, _ in VALUE_FORMS:
        assert _VALUE.match(form.split(" / ")[0]) or form == "状態の名前・数" or form == '"文字"', form


def test_when_the_engine_does_not_fire_is_stopped(tmp_path):
    from ponte.checker import check
    from ponte.parser import parse_file
    src = open("spec/lend.ponte", encoding="utf-8").read().replace("user taps return-button on Loan", "user swipes card left", 1)
    p = tmp_path / "x.ponte"
    p.write_text(src, encoding="utf-8")
    msgs = [f.message for f in check(parse_file(str(p))) if f.code == "E07"]
    assert any("まだ実行エンジンが起こしません" in m for m in msgs), msgs


def test_rules_guide_lists_everything():
    from ponte.forms import DO_FORMS, WHEN_FORMS
    from ponte.guide import rules_guide
    g = rules_guide()
    assert all(f[1] in g for f in DO_FORMS) and all(f[1] in g for f in WHEN_FORMS)


def test_list_literal_in_do():
    assert run("sum of [1, 2, 3]", "") == 6
    assert run('[t, "b"]', "a") == ["a", "b"]
    assert run('take 1 of sort ["c", "a", "b"]', "") == ["a"]
    assert run('["朝", "昼"] contains "夜"', "") == "no"
    assert run("count of []", "") == 0
