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



PAY_SPEC = """thing Order
  item    text
  status  [new | paid]

flow Order.status
  new -> paid

who
  user  can see     Order
  user  can change  Order

connect Pay
  does     charge amount  item text -> done | failed
  by       python "pay.py"
  with     timeout 5 seconds
  confirm  timeout

rule Checkout
  when   user taps pay-button on Order
  where  status is new
  do     Pay charge amount {item}

rule MarkPaid
  do     move this to paid

rule PayFailed
  do     notify me "支払いに失敗しました"

relate
  Checkout  then  MarkPaid
  Checkout  else  PayFailed
"""

PAY_PY = '''from ponte.report import report
class Client:                                 # 本物の HTTP クライアントのように、使う値を自分で持つ
    def __init__(self, timeout=30): self.timeout = timeout
def charge_amount(text, settings):
    c = CLIENT
    report(timeout=c.timeout)
    return "done"
'''


@pytest.mark.parametrize("client,status", [("Client(timeout=settings['timeout'])", "paid"), ("Client()", "new")])
def test_connect_timeout_that_the_client_ignores_is_caught(tmp_path, client, status):
    from ponte.runtime import Engine
    (tmp_path / "pay.py").write_text(PAY_PY.replace("CLIENT", client), encoding="utf-8")
    p = tmp_path / "pay.ponte"
    p.write_text(PAY_SPEC, encoding="utf-8")
    s = parse_file(str(p))
    assert [f for f in check(s) if f.is_error] == []
    eng = Engine(s)
    me = eng.login("me")
    o = eng.create("Order", {"item": "本", "status": "new"}, me, fire=False, check=False)
    eng.tap(me, "pay-button", "Order", o.id)
    assert eng.boxes["Order"][o.id].values["status"] == status
    if status == "new":                                                                # 失敗の逃げ道に進み、理由も知らせる
        texts = [n["text"] for n in eng.notifications]
        assert "支払いに失敗しました" in texts and any("confirm timeout" in t and "30" in t for t in texts), texts


def test_within_allows_only_the_written_tolerance():
    from ponte.confirm import problems, tolerances
    t = tolerances("pretrained_checksum 1234.5 within 0.01%")
    decl, shown = {"pretrained_checksum": 1234.5}, {"pretrained_checksum": "1234.5"}
    assert problems(decl, ["pretrained_checksum"], {"pretrained_checksum": 1234.55}, shown, t) == []   # GPU の揺れ
    bad = problems(decl, ["pretrained_checksum"], {"pretrained_checksum": 1240.2}, shown, t)            # 重みが変わった
    assert bad and "1234.5" in bad[0] and "1240.2" in bad[0]                                           # 実測値を必ず出す
    assert problems(decl, ["pretrained_checksum"], {"pretrained_checksum": 1234.55}, shown)            # within が無ければほぼ完全一致


def test_within_is_readable_by_check():
    assert codes('job J\n  run  python t.py\n  confirm  pretrained_checksum 1234.5 within 0.01%\n') == []
