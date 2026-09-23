"""標準ライブラリ（use std/...）と、そのために足した道具。"""
import os
from datetime import datetime

import pytest

from ponte.body import BodyError, body_of
from ponte.checker import check
from ponte.examples import holes, run_examples
from ponte.parser import STD_DIR, ParseError, parse, parse_file
from ponte.runtime import Engine

STD = sorted(f[:-len(".ponte")] for f in os.listdir(STD_DIR) if f.endswith(".ponte"))


def use(name, tmp_path):
    p = tmp_path / "t.ponte"
    p.write_text(f"use std/{name}\n", encoding="utf-8")
    return parse_file(str(p))


@pytest.mark.parametrize("name", STD)
def test_every_std_file_checks_and_passes_its_examples(name, tmp_path):
    spec = use(name, tmp_path)
    assert [f for f in check(spec) if f.is_error] == []
    res = run_examples(spec)
    assert res and all(r.ok for r in res), [r for r in res if not r.ok]
    assert holes(spec, res) == []


def test_unknown_std_lists_what_exists(tmp_path):
    with pytest.raises(ParseError) as e:
        use("nope", tmp_path)
    assert "std/date" in e.value.message and "std/money" in e.value.message


def body(src):
    spec = parse(src)
    a = spec.find("action", "A")
    return body_of(a, a.child("do"), {s.name: s for s in spec.decls("shape")})


HEAD = "action A\n  in t text\n  out found text | missing\n  example \"x\" -> missing\n  else skip\n"


def test_plus_binds_after_of():
    b = body(HEAD + "  do\n    a = find all D in t\n    b = find all D in t\n    n = count of a + count of b - 1\n\nshape D\n  digits 1\n")
    assert b.run({"t": "1 2"}) == 3


def test_state_name_cannot_be_a_line_name():
    with pytest.raises(BodyError) as e:
        body(HEAD + "  do\n    back = trim t\n    side[front | back] = match back\n      \"a\" -> front\n      else -> back\n")
    assert "同じ" in e.value.message


def test_word_with_is_ascii_and_part_access():
    b = body(HEAD + "  do\n    hits = find all E in t\n    who = user of first of hits\n\nshape E\n  user word with \".\" 1..20\n  \"@\"\n")
    assert b.run({"t": "連絡はtaro.y@x"}) == "taro.y"


def test_kakeibo_uses_std_money():
    spec = parse_file("spec/kakeibo.ponte")
    assert [f for f in check(spec) if f.is_error] == []
    res = run_examples(spec)
    assert all(r.ok for r in res) and holes(spec, res) == []
    e = Engine(spec, clock=lambda: datetime(2026, 9, 23, 12, 0), parallel=False)
    me = e.login("me")
    a = e.create("Expense", {"memo": "本 ￥２，２００"}, me)
    g = e.create("Expense", {"memo": "ガム"}, me)
    assert a.values["yen"] == "2200" and g.values["yen"] == ""
    assert e.notifications == []                      # 拾えない時は静かに（skip）

    from ponte.server import App
    v = App(spec, e).view("Home", me, {}, None, None, "ja")
    stats = [b for s in v["slots"] for b in s["blocks"] if b.get("type") == "stats"][0]["items"]
    assert [(x["label"], x["value"]) for x in stats] == [("メモの数", "2"), ("金額の合計", "2,200")]


def test_set_value_is_checked():
    spec = parse_file("spec/kakeibo.ponte")
    src = open("spec/kakeibo.ponte", encoding="utf-8").read().replace("do    set yen to result", "do    set yen to (result)")
    found = [f.code for f in check(parse(src))]
    assert "E31" in found and spec is not None


def test_shape_uses_other_shape():
    b = body(HEAD + "  do\n    hits = find all D in t\n    h = hour of first of hits\n\nshape D\n  digits 1..2\n  \"/\"\n  digits 1..2\n  maybe Clock\n\nshape Clock\n  space\n  hour digits 1..2\n  \":\"\n  digits 2\n")
    assert b.run({"t": "締切 10/15 18:30"}) == "18"


def test_shape_cycle_is_error():
    import pytest
    from ponte.body import BodyError
    with pytest.raises(BodyError, match="自分に戻って"):
        body(HEAD + "  do\n    hits = find all A in t\n    n = count of hits\n\nshape A\n  \"a\"\n  maybe B\n\nshape B\n  A\n")


def test_single_language_app_writes_ui_text_directly(tmp_path):
    from ponte.checker import check
    s = open("spec/todo.ponte", encoding="utf-8").read()
    s = s[:s.index("words ja")].replace("named finish", 'named "終わった"').replace("empty   todo-empty", 'empty   "まだありません"')
    assert not [f for f in check(parse(s)) if f.code.startswith("E")]
