"""画面のために足した言語の小さな部品のテスト。"""
from datetime import datetime

from lang.body import Body, in_range
from lang.checker import check
from lang.parser import parse, parse_file, split_comment


def test_hex_color_is_not_a_comment():
    assert split_comment("  color main  #4F46E5") == ("  color main  #4F46E5", None, False)
    assert split_comment("  x  # コメント")[1] == "コメント"
    assert split_comment("  x ## 待って")[2] is True


def test_number_ranges_in_match():
    assert in_range(-3, "..-1") and in_range(2, "1..3") and in_range(9, "4..")
    assert not in_range(0, "..-1") and not in_range(4, "1..3") and not in_range("a", "1..3")


def test_part_computes_days_and_urgency():
    spec = parse_file("spec/hub_app.lang")
    p = spec.find("part", "DeadlineBadge")
    lines = [c for c in p.children if "=" in c.raw]
    body = Body(p, {}, ["deadline"], {}, single_result=False, lines=lines)
    now = datetime(2026, 9, 21, 21, 0)
    for d, want in [("9/20 10:00", "over"), ("9/21 23:59", "today"), ("9/24 9:00", "soon"), ("10/1 9:00", "later")]:
        assert body.values({"deadline": d, "__now__": now})["urgency"] == want


def test_app_spec_passes_publish_check():
    from lang.checker import Options
    assert [f.code for f in check(parse_file("spec/hub_app.lang"), Options(publish=True))] == []


def test_days_until_is_not_until():
    spec = parse("action A\n  in x text\n  out n number\n  example \"a\" -> 1\n  example \"b\" -> 2\n  else skip\n  by ai\n  do\n    n = days until x\n")
    assert "E02" not in [f.code for f in check(spec)]
