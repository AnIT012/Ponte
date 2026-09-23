"""E32: rule ごとに this が何の thing かを決めて、項目と値の型を動かす前に確かめる。"""
import re

import pytest

from ponte.checker import check, rule_result, rule_this
from ponte.parser import parse_file


def e32(path, old, new, tmp_path):
    src = open(path, encoding="utf-8").read()
    for o, n in ([(old, new)] if isinstance(old, str) else zip(old, new)):
        assert re.search(o, src), o
        src = re.sub(o, n, src, count=1)
    p = tmp_path / "x.ponte"
    p.write_text(src, encoding="utf-8")
    return [f.message for f in check(parse_file(str(p))) if f.code == "E32"]


def test_this_and_result_are_inferred():
    lend = parse_file("spec/lend.ponte")
    t = rule_this(lend)
    assert t["Borrow"] == "Item" and t["MarkLent"] == "Loan" and t["MakeAdmin"] == "User"
    k = parse_file("spec/kakeibo.ponte")
    assert rule_this(k)["SaveYen"] == "Expense"                 # then でつながった先
    assert rule_result(k)["SaveYen"] == "number"                # FindYen の答えの型


@pytest.mark.parametrize("path", ["spec/hub_app.ponte", "spec/lend.ponte", "spec/kakeibo.ponte"])
def test_apps_have_no_type_errors(path):
    assert [f for f in check(parse_file(path)) if f.code == "E32"] == []


CASES = [
    ("spec/lend.ponte", r"move this to returned", "move this to retrned", "という状態はありません"),
    ("spec/lend.ponte", r"move item of this to lent", "move item of this to lnet", "Item に「lnet」"),
    ("spec/lend.ponte", r"move item of this to lent", "move borrower of this to lent", "User に「lent」"),
    ("spec/lend.ponte", r"item\s+this\n", "item  me\n", "item は Item なのに、me は User"),
    ("spec/lend.ponte", r"\{item\} の返却日", "{itm} の返却日", "{itm}"),
    ("spec/lend.ponte", r"where\s+status is free", "where  staus is free", "list FreeItems: Item に「staus」"),
    ("spec/lend.ponte", r"(borrow-button on Item\n\s+)where\s+status is free", r"\1where  staus is free", "rule Borrow: Item に「staus」"),
    ("spec/kakeibo.ponte", r"sum yen of Mine", "sum memo of Mine", "足せません"),
    ("spec/kakeibo.ponte", r"set yen to result", "set yen to me", "number なのに、me は User"),
    ("spec/kakeibo.ponte", r"FindYen with memo", "FindYen with mem", "「mem」"),
    ("spec/kakeibo.ponte", (r"use std/money", r"FindYen with memo"), ("use std/money\nuse std/contact", "FindEmail with memo"),
     "number なのに、result は text"),
    ("spec/kakeibo.ponte", r"relate\n  ReadYen then SaveYen", "relate\n  OpenAdd then SaveYen", "this が何の thing か決まりません"),
]


@pytest.mark.parametrize("path,old,new,want", CASES)
def test_type_mistakes_are_caught_before_running(path, old, new, want, tmp_path):
    msgs = e32(path, old, new, tmp_path)
    assert any(want in m for m in msgs), msgs
