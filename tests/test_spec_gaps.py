"""仕様にあったのに動かなかったもの（REVIEW C）のテスト。"""
import json
import time
from datetime import datetime

import pytest

from ponte.parser import parse, parse_file
from ponte.runtime import Ctx, Engine, NotAllowed, RuleError

NOW = datetime(2026, 9, 21, 9, 0)

GONE = """
thing Company
  name  text

thing Job
  title    text
  company  Company  gone[{mode}]

who
  user can do everything
"""


@pytest.mark.parametrize("mode, jobs_left, company_field", [("remove too", 0, None), ("leave empty", 1, "")])
def test_remove_follows_gone(mode, jobs_left, company_field):
    e = Engine(parse(GONE.format(mode=mode)), clock=lambda: NOW)
    me = e.login("me")
    c = e.create("Company", {"name": "A"}, me)
    e.create("Job", {"title": "x", "company": c.id}, me)
    e.remove(c, me)
    assert len(e.all("Job")) == jobs_left
    if company_field is not None:
        assert e.all("Job")[0].values["company"] == company_field


def test_remove_blocked():
    e = Engine(parse(GONE.format(mode="block")), clock=lambda: NOW)
    me = e.login("me")
    c = e.create("Company", {"name": "A"}, me)
    e.create("Job", {"title": "x", "company": c.id}, me)
    with pytest.raises(RuleError):
        e.remove(c, me)
    assert len(e.all("Company")) == 1


def test_remove_needs_who_and_goes_home():
    e = Engine(parse_file("spec/hub_app.ponte"), clock=lambda: NOW)
    me, other = e.login("me"), e.login("other")
    a = e.create("Application", {"company": "A"}, me)
    with pytest.raises(NotAllowed):
        e.remove(a, other)
    ctx = e.tap(me, "delete-button", "Application", a.id)       # remove this → then GoHome
    assert e.all("Application") == [] and ctx.nav == "Home"


def test_change_moves_old_data(tmp_path):
    store = tmp_path / "d.jsonl"
    v1 = "thing A\n  name text\n  status[new | old | gone]\n\nwho\n  user can do everything\n"
    e = Engine(parse(v1), store=str(store), clock=lambda: NOW)
    e.create("A", {"name": "x", "status": "gone"}, None, fire=False, check=False)
    v2 = ("thing A\n  title text\n  memo text\n  status[new | old]\n\nwho\n  user can do everything\n\n"
          "change A to v2\n  rename name to title\n  add memo text = \"-\"\n  remove state gone -> old\n")
    e2 = Engine(parse(v2), store=str(store), clock=lambda: NOW)
    assert e2.all("A")[0].values == {"title": "x", "memo": "-", "status": "old"}


HOW = """
action Slow
  in      x text
  out     r text
  example "a" -> "a"
  example "b" -> "b"
  else    skip
  by      code "slow.ponte"
  how
    limit 0.2 seconds
    on failure retry 2 times
"""


def test_how_limit_and_retry():
    e = Engine(parse(HOW), clock=lambda: NOW)
    calls = []

    def flaky(x):
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("まだ")
        return "ok"
    e.action_impls["Slow"] = flaky
    assert e.run_action("Slow", Ctx(None, payload="a")) == "ok" and len(calls) == 3   # 2回やり直して3回目で通る

    e.action_impls["Slow"] = lambda x: time.sleep(1) or "late"
    with pytest.raises(RuleError):
        e.run_action("Slow", Ctx(None, payload="a"))                                    # 0.2秒を過ぎたら失敗


ASK = """
action Classify
  in      mail text
  out     passed | failed | unknown
  example "通過のお知らせ" -> passed
  example "ご縁がなく"     -> failed
  else    use default unknown
  ask     ai
  how
    limit 5 seconds
"""


def test_ask_ai_uses_reply_only_in_the_out_form():
    from ponte.body import Tagged
    e = Engine(parse(ASK), clock=lambda: NOW)
    e.ask_client = lambda messages: "passed"
    assert e.run_action("Classify", Ctx(None, payload="選考通過")) == Tagged("passed")
    e.ask_client = lambda messages: "たぶん通ってると思います！"                   # 形が違う答えは使わず else へ
    assert e.run_action("Classify", Ctx(None, payload="?")) == "unknown"


def test_use_imports_other_file_and_maps_lines(tmp_path):
    (tmp_path / "parts.ponte").write_text("part Header\n  show  text \"x\"\n\nmatch A.s to color\n  a -> red\n", encoding="utf-8")
    (tmp_path / "main.ponte").write_text('use "parts.ponte"\n\nthing A\n  s[a | b]\n\nwho\n  user can see A\n', encoding="utf-8")
    spec = parse_file(str(tmp_path / "main.ponte"))
    assert {d.name for d in spec.decls()} >= {"Header", "A.s"}
    from ponte.checker import check
    f = next(f for f in check(spec) if f.code == "E01")                              # match の b が無い（取り込んだ方のエラー）
    assert spec.where(f.line) == (str(tmp_path / "parts.ponte"), 4)


def test_input_from_now_is_enforced_by_server():
    import threading
    import urllib.request
    from ponte.server import serve
    e = Engine(parse_file("spec/hub_app.ponte"), clock=lambda: NOW)
    httpd = serve(e.spec, e, port=0, ticker=False)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(f"http://127.0.0.1:{httpd.server_address[1]}/api/submit",
                                 json.dumps({"user": "me", "input": "AddApplication", "values": {"company": "X", "deadline": "2026-09-20T10:00"}}).encode(),
                                 {"content-type": "application/json"})
    try:
        op.open(req)
        raise AssertionError("過去の締切が通ってしまった")
    except urllib.error.HTTPError as err:
        assert "今より後" in json.loads(err.read())["error"]
    finally:
        httpd.shutdown()
