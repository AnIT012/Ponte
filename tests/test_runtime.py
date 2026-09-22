"""実行エンジンと画面のテスト（仕様 v0.2）。"""
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import pytest

from lang.examples import run_examples
from lang.parser import parse, parse_file
from lang.runtime import Engine, NotAllowed, RuleError
from lang.server import serve

NOW = datetime(2026, 9, 21, 21, 0)   # 9/21 21:00
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
    e = engine("spec/hub_ready.lang")          # 中身（.ai）がまだ無い spec
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
    assert got == [{"company": "Keep", "deadline": "9/24 23:59", "memo": "", "owner": me.id, "status": "submitted"}]
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

    def view(scene="Home", **q):
        qs = urllib.parse.urlencode({"scene": scene, "user": "me", **q})
        return json.loads(opener.open(base + "/api/view?" + qs).read())

    def blocks(v, slot):
        return next(s["blocks"] for s in v["slots"] if s["slot"] == slot)
    try:
        page = opener.open(base + "/").read().decode()
        assert 'id="root"' in page and "--main:#4F46E5" in page          # style theme の色が効いている
        v = view()
        assert [b["type"] for b in blocks(v, "top")] == ["part", "tabs", "button"]
        assert blocks(v, "main")[0]["type"] == "items" and blocks(v, "main")[0]["rows"] == []   # 空 → empty の文
        assert blocks(v, "main")[0]["empty"].startswith("3日以内")
        assert post("/api/tap", {"user": "me", "button": "add", "on": "Home"})["nav"] == "AddApplication"
        assert blocks(view("AddApplication"), "top")[0]["name"] == "Header"
        assert post("/api/submit", {"user": "me", "input": "AddApplication",
                                    "values": {"company": "Web", "deadline": "2026-09-23T10:00"}})["ok"]
        row = blocks(view(), "main")[0]["rows"][0]
        assert row["title"] == "Web" and row["mark"]["label"] == "下書き"
        assert row["sub"]["lines"] == ["9/23 10:00 ・ あと2日"] and row["sub"]["mark"]["value"] == "soon"
        # タブ（画面の状態）で見せ方が変わる
        assert blocks(view(state=json.dumps({"tab": "board"})), "main")[0]["type"] == "board"
        assert blocks(view(state=json.dumps({"tab": "calendar"})), "main")[0]["items"][0]["date"] == "2026-09-23"
        assert blocks(view(state=json.dumps({"menu": "open"})), "over")[0]["type"] == "dialog"
        # 詳しく: flow で動けないボタンは押せない
        r = post("/api/tap", {"user": "me", "button": "card", "on": "Mine", "id": row["id"]})
        assert r["nav"] == "Detail"
        d = blocks(view("Detail", this=row["id"], origin="Mine"), "main")[0]
        assert [(b["label"], bool(b.get("disabled"))) for b in d["buttons"]] == [("提出した", False), ("通過", True), ("不合格", True)]
        # board で動かす: flow に無い流れは人の言葉で断る
        bad = post("/api/drag", {"user": "me", "id": row["id"], "to": "passed"})
        assert "「下書き」から「通過」へは動かせません" in bad["error"]
        assert post("/api/drag", {"user": "me", "id": row["id"], "to": "submitted"})["ok"]
        assert blocks(view(), "main")[0]["rows"] == []                  # DueSoon から抜けた
        assert "error" in post("/api/submit", {"user": "me", "input": "AddApplication", "values": {"company": "X", "deadline": "来週"}})
        en = view(lang="en", state=json.dumps({"tab": "all"}))
        assert blocks(en, "main")[0]["rows"][0]["mark"]["label"] == "Submitted"
    finally:
        httpd.shutdown()
