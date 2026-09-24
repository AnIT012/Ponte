"""with と confirm（仕様 5章）: 宣言した値が下の層で本当に効いたか。黙って捨てられたら止める。"""
import textwrap

import pytest

from ponte.checker import check
from ponte.examples import run_examples
from ponte.parser import parse, parse_file

SPEC = """action Train
  in       data text
  out      done text
  example  "x" -> done "ok"
  example  "y" -> done "ok"
  else     skip
  by       python "train.py"
  with     lr 1.25e-4, batch 32, pretrained yes, timeout 5 seconds
  confirm  lr, batch, pretrained, timeout
"""

HONEST = '''
from ponte.report import report
class Adam:                                   # 本物の optimizer のように、使う値を自分で持つ
    def __init__(self, lr=1e-3): self.param_groups = [{"lr": lr}]
def answer(value, settings):
    opt = Adam(lr=settings["lr"])
    report(lr=opt.param_groups[0]["lr"], batch=settings["batch"], pretrained=True, timeout="5000 ms")
    return 'done "ok"'
'''

DROPPED = HONEST.replace('opt = Adam(lr=settings["lr"])', 'opt = Adam()')          # ⑥: lr= を書き忘れて既定値のまま
FORGOT = HONEST.replace("pretrained=True", "pretrained=False")                      # ⑤: 事前学習を読み忘れた
SILENT = HONEST.replace(", timeout=\"5000 ms\"", "")                                # 報告しない値は、効いたとみなさない


def run(tmp_path, body, spec=SPEC):
    (tmp_path / "train.py").write_text(textwrap.dedent(body), encoding="utf-8")
    p = tmp_path / "exp.ponte"
    p.write_text(spec, encoding="utf-8")
    s = parse_file(str(p))
    assert [f for f in check(s) if f.is_error] == []
    return run_examples(s)


def test_values_that_really_took_effect_pass(tmp_path):
    res = run(tmp_path, HONEST)
    assert res and all(r.ok for r in res)


@pytest.mark.parametrize("body,name", [(DROPPED, "lr"), (FORGOT, "pretrained"), (SILENT, "timeout")])
def test_a_value_dropped_below_is_caught(tmp_path, body, name):
    res = run(tmp_path, body)
    bad = [r for r in res if not r.ok]
    assert bad and f"confirm {name}" in bad[0].message, [r.message for r in res]


def test_message_says_what_was_declared_and_what_was_used(tmp_path):
    msg = [r for r in run(tmp_path, DROPPED) if not r.ok][0].message
    assert "1.25e-4" in msg and "0.001" in msg


def codes(src):
    return [f.code for f in check(parse(src)) if f.is_error]


def test_confirm_must_name_something_declared():
    assert "E32" in codes(SPEC.replace("confirm  lr, batch", "confirm  lr, bacth"))


def test_with_and_confirm_only_where_a_lower_layer_does_the_work():
    assert "E31" in codes(SPEC.replace('  by       python "train.py"\n', ""))


def test_with_must_be_readable():
    assert "E31" in codes(SPEC.replace("with     lr 1.25e-4,", "with     lr,"))


def test_report_works_without_ponte_inside_a_separate_process(tmp_path, monkeypatch):
    import json
    from ponte.report import report
    out = tmp_path / "used.jsonl"
    monkeypatch.setenv("PONTE_REPORT", str(out))
    report(lr=0.001, batch=32)
    assert json.loads(out.read_text(encoding="utf-8").splitlines()[0]) == {"lr": 0.001, "batch": 32}


def test_running_app_does_not_use_an_answer_whose_values_did_not_take_effect(tmp_path):
    from ponte.runtime import Ctx, Engine
    (tmp_path / "train.py").write_text(textwrap.dedent(DROPPED), encoding="utf-8")
    p = tmp_path / "exp.ponte"
    p.write_text(SPEC.replace("else     skip", 'else     use default done "fallback"'), encoding="utf-8")
    eng = Engine(parse_file(str(p)))
    me = eng.login("me")
    ctx = Ctx(me)
    ctx.payload = "x"
    assert eng.run_action("Train", ctx) == 'done "fallback"'                            # 答えは使わず else
    assert any("confirm lr" in n["text"] for n in eng.notifications)                    # 理由は知らせる
