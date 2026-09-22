"""実行エンジンと画面のテスト（仕様 v0.2）。"""
import json
import threading
import urllib.error
import urllib.request
from datetime import datetime

import pytest

from lang.examples import run_examples
from lang.parser import parse, parse_file
from lang.runtime import Engine, NotAllowed, RuleError
from lang.server import serve

NOW = datetime(2026, 9, 21, 21, 0)
APP = "spec/hub_app.lang"


def engine(path=APP, **kw):
    return Engine(parse_file(path), clock=lambda: NOW, **kw)


def test_examples_pass():
    for path in ("spec/hub_ready.lang", APP):
        results = run_examples(parse_file(path))
        assert results and all(r.ok for r in results), [r for r in results if not r.ok]


def test_flow_and_conflict():
    e = engine()
    me = e.login("me")
    a = e.create("Application", {"company": "A", "deadline": "9/24 23:59"}, me)
    with pytest.raises(RuleError):
        e.move(a, "passed", me)                 # draft から passed には飛べない
    e.move(a, "submitted", me)
    e.move(a, "passed", me)
    e.move(a, "failed", me)                     # failed > passed で上書き
    assert a.values["status"] == "failed"
    b = e.create("Application", {"company": "B", "status": "submitted"}, me)
    e.move(b, "failed", me)
    e.move(b, "passed", me)                     # 負ける方は何もしない（エラーにもしない）
    assert b.values["status"] == "failed"


def test_same_box_is_serialized():
    e = engine()
    me = e.login("me")
    a = e.create("Application", {"company": "A"}, me)
    errors = []

    def go():
        try:
            e.move(a, "submitted", me)
        except RuleError as x:
            errors.append(x)
    ts = [threading.Thread(target=go) for _ in range(50)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert a.values["status"] == "submitted" and not errors


def test_list_within_and_sort():
    e = engine()
    me = e.login("me")
    for c, d, s in [("late", "9/30 10:00", "draft"), ("soon", "9/24 23:59", "draft"),
                    ("sooner", "9/22 9:00", "draft"), ("done", "9/22 9:00", "submitted"), ("past", "9/20 9:00", "draft")]:
        e.create("Application", {"company": c, "deadline": d, "status": s}, me, fire=False)
    from lang.runtime import Ctx
    assert [b.values["company"] for b in e.list_items("DueSoon", Ctx(me))] == ["sooner", "soon"]


def test_who_hides_other_peoples_data():
    e = engine()
    me, other = e.login("me"), e.login("other")
    a = e.create("Application", {"company": "Mine", "deadline": "9/23 10:00"}, me)
    from lang.runtime import Ctx
    assert e.list_items("DueSoon", Ctx(other)) == []
    with pytest.raises(NotAllowed):
        e.move(a, "submitted", other)


def test_reminder_goes_to_owner():
    e = engine()
    me = e.login("me")
    e.create("Application", {"company": "Osaka Gas", "deadline": "9/24 23:59"}, me)
    e.tick(NOW)
    e.tick(NOW)                                  # 同じ分に2回動かない
    assert [(n["rule"], n["user"]) for n in e.notifications] == [("Remind", "me")]


def test_tap_moves_only_this_and_relate_wins():
    e = engine()
    me = e.login("me")
    a = e.create("Application", {"company": "A", "deadline": "9/23 10:00"}, me)
    b = e.create("Application", {"company": "B", "deadline": "9/23 10:00"}, me)
    e.tap(me, "submitted-button", "DueSoon", a.id)
    assert (a.values["status"], b.values["status"]) == ("submitted", "draft")
    assert e.tap(me, "add", "Home").nav == "AddApplication"


def test_action_without_body_goes_to_else():
    e = engine()
    e.gives("Gmail", "new message", "【締切9/24 23:59】")
    assert "確認してください" in e.notifications[-1]["text"]


RELATE = """
thing Job
  name  text
  step[new | read | filed]

flow Job.step
  new -> read -> filed

who
  user can do everything

rule A
  when  Job is created
  do    notify "A"

rule B
  do    notify "B"

rule C
  when  Job is created
  do    notify "C"

rule D
  do    move this to filed

rule E
  do    notify "E"

relate
  A then B
  A before C
  D else E

rule F
  when  user says "go {name}"
  do    move Job where name is {name} to read

rule G
  when  Job moves to read
  do    move this to filed
"""


def test_relate_then_before_else():
    e = Engine(parse(RELATE), clock=lambda: NOW, parallel=False)
    me = e.login("me")
    j = e.create("Job", {"name": "x"}, me)
    texts = [n["text"] for n in e.notifications]
    assert texts.index("A") < texts.index("B") and "C" in texts
    e.run_rule(e.rules["D"], __import__("lang.runtime", fromlist=["Ctx"]).Ctx(me, this=j))   # new -> filed は動けない → else E
    assert e.notifications[-1]["text"] == "E"
    e.says(me, "go x")                          # {name} で絞って move、moves to read で G が続く
    assert j.values["step"] == "filed"


def test_data_survives_restart(tmp_path):
    store = str(tmp_path / "d.jsonl")
    e = engine(store=store)
    me = e.login("me")
    a = e.create("Application", {"company": "Keep", "deadline": "9/24 23:59"}, me)
    e.move(a, "submitted", me)
    e2 = engine(store=store)
    got = [b.values for b in e2.all("Application")]
    assert got == [{"company": "Keep", "deadline": "9/24 23:59", "owner": me.id, "status": "submitted"}]
    assert e2.create("Application", {"company": "New"}, e2.login("me")).id not in {b.id for b in e.all("Application")}


def test_server_end_to_end():
    e = engine()
    httpd = serve(parse_file(APP), e, port=0, ticker=False)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = f"http://127.0.0.1:{port}"

    def post(path, body):
        req = urllib.request.Request(base + path, json.dumps(body).encode(), {"content-type": "application/json"})
        try:
            return json.loads(opener.open(req).read())
        except urllib.error.HTTPError as err:       # 400 はエラーの中身を返す
            return json.loads(err.read())

    def view():
        return json.loads(opener.open(base + "/api/view?scene=Home&user=me").read())
    try:
        assert 'id="root"' in opener.open(base + "/").read().decode()
        assert view()["slots"][1]["blocks"][0]["text"].startswith("3日以内")
        assert post("/api/tap", {"user": "me", "button": "add", "on": "Home"})["nav"] == "AddApplication"
        assert post("/api/submit", {"user": "me", "input": "AddApplication", "values": {"company": "Web", "deadline": "9/23 10:00"}})["ok"]
        rows = view()["slots"][1]["blocks"][0]["rows"]
        assert rows[0]["title"] == "Web" and rows[0]["mark"]["label"] == "draft"
        post("/api/tap", {"user": "me", "button": "submitted-button", "on": "DueSoon", "id": rows[0]["id"]})
        assert view()["slots"][1]["blocks"][0]["type"] == "text"      # DueSoon が空になった
        bad = post("/api/submit", {"user": "me", "input": "AddApplication", "values": {"company": "X", "deadline": "来週"}})
        assert "error" in bad
    finally:
        httpd.shutdown()
