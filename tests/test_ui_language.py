"""画面のために足した言語の小さな部品のテスト。"""
from datetime import datetime

from ponte.body import Body, in_range
from ponte.checker import check
from ponte.parser import parse, parse_file, split_comment


def test_hex_color_is_not_a_comment():
    assert split_comment("  color main  #4F46E5") == ("  color main  #4F46E5", None, False)
    assert split_comment("  x  # コメント")[1] == "コメント"
    assert split_comment("  x ## 待って")[2] is True


def test_number_ranges_in_match():
    assert in_range(-3, "..-1") and in_range(2, "1..3") and in_range(9, "4..")
    assert not in_range(0, "..-1") and not in_range(4, "1..3") and not in_range("a", "1..3")


def test_part_computes_days_and_urgency():
    spec = parse_file("spec/hub_app.ponte")
    p = spec.find("part", "DeadlineBadge")
    lines = list(p.child("do").children)
    body = Body(p, {}, ["deadline"], {}, single_result=False, lines=lines)
    now = datetime(2026, 9, 21, 21, 0)
    for d, want in [("9/20 10:00", "over"), ("9/21 23:59", "today"), ("9/24 9:00", "soon"), ("10/1 9:00", "later")]:
        assert body.values({"deadline": d, "__now__": now})["urgency"] == want


def test_app_spec_passes_publish_check():
    from ponte.checker import Options
    assert [f.code for f in check(parse_file("spec/hub_app.ponte"), Options(publish=True))] == []


def test_days_until_is_not_until():
    spec = parse("action A\n  in x text\n  out n number\n  example \"a\" -> 1\n  example \"b\" -> 2\n  else skip\n  by ai\n  do\n    n = days until x\n")
    assert "E02" not in [f.code for f in check(spec)]


def test_parse_button():
    from ponte.parser import parse_button
    b = parse_button('failed-button    named 不合格 icon x confirm "不合格にしますか？"')
    assert (b["id"], b["label"], b["icon"], b["confirm"]) == ("failed-button", "不合格", "x", "不合格にしますか？")
    assert parse_button("menu named メニュー toggle menu")["act"] == {"kind": "toggle", "state": "menu"}
    assert parse_button("x named y bogus z") is None


def test_words_quoted_keys():
    from ponte.parser import words_entries
    w = parse('words en\n  draft  Draft\n  "あと{left}日"   {left} days left\n').decls("words")[0]
    assert words_entries(w) == {"draft": "Draft", "あと{left}日": "{left} days left"}


def test_update_refuses_state_fields():
    import pytest
    from ponte.runtime import Engine, RuleError
    e = Engine(parse_file("spec/hub_app.ponte"), clock=lambda: datetime(2026, 9, 21))
    me = e.login("me")
    a = e.create("Application", {"company": "A"}, me)
    e.update(a, {"memo": "hi"}, me)
    assert a.values["memo"] == "hi"
    with pytest.raises(RuleError):
        e.update(a, {"status": "passed"}, me)            # 状態は move でしか変えられない
    with pytest.raises(RuleError):
        e.update(a, {"memo": "x"}, e.login("other"))     # who


def test_sort_desc():
    from ponte.runtime import Ctx, Engine
    spec = parse("thing A\n  d monthday\n\nwho\n  user can see A\n\nlist L\n  of    A\n  sort  d desc\n")
    e = Engine(spec, clock=lambda: datetime(2026, 9, 1))
    for d in ["9/2 10:00", "9/9 10:00", "9/5 10:00"]:
        e.create("A", {"d": d}, None, fire=False, check=False)
    assert [b.values["d"] for b in e.list_items("L", Ctx(None))] == ["9/9 10:00", "9/5 10:00", "9/2 10:00"]
    bad = parse("thing A\n  d monthday\n\nwho\n  user can see A\n\nlist L\n  of    A\n  sort  d down\n")
    assert "E28" in [f.code for f in check(bad)]


def test_never_fail_and_return_empty():
    from ponte import fill as F
    spec = parse_file("spec/hub_app.ponte")
    a = spec.find("action", "ExtractDeadline")
    crash = "```lang\ndo\n  hits = find all D in mail\n  r = found monthday of first of hits\n\nshape D\n  month digits 1..2\n  \"/\"\n  day digits 1..2\n  space\n  hour digits 1..2\n  \":\"\n  minute digits 2\n```"
    probs = F.verify(spec, a, F.extract_code(crash)).problems
    assert any(p.startswith("never fail") for p in probs)          # 見つからない時に first of で止まる
    empty_spec = parse(open("spec/hub_app.ponte", encoding="utf-8").read().replace("never    fail", "never    return empty"))
    ea = empty_spec.find("action", "ExtractDeadline")
    empty = "```lang\ndo\n  r = found \" \"\n```"
    assert any(p.startswith("never return empty") for p in F.verify(empty_spec, ea, F.extract_code(empty)).problems)


def test_take_limits_rows_in_view():
    from ponte.runtime import Engine
    from ponte.server import App
    e = Engine(parse_file("spec/hub_app.ponte"), clock=lambda: datetime(2026, 9, 21))
    me = e.login("me")
    for i in range(25):
        e.create("Application", {"company": f"C{i}", "deadline": "10/1 10:00"}, me, fire=False)
    v = App(e.spec, e).view("Home", me, {"tab": "all"}, None, None, "ja")
    b = [b for s in v["slots"] if s["slot"] == "main" for b in s["blocks"]][0]
    assert b["take"] == 20 and len(b["rows"]) == 25 and b["more"] == "もっと見る"
