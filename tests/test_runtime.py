"""実行エンジンと画面のテスト（仕様 v0.2）。"""
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import pytest

from ponte.examples import run_examples
from ponte.parser import parse, parse_file
from ponte.runtime import Engine, NotAllowed, RuleError
from ponte.server import serve

NOW = datetime(2026, 9, 21, 21, 0)   # 9/21 21:00
APP = "spec/hub_app.ponte"


def engine(path=APP, **kw):
    return Engine(parse_file(path), clock=lambda: NOW, **kw)


def test_examples_pass():
    for path in ("spec/hub_ready.ponte", APP):
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
    from ponte.runtime import Ctx
    assert [b.values["company"] for b in e.list_items("DueSoon", Ctx(me))] == ["sooner", "soon"]


def test_who_hides_other_peoples_data():
    e = engine()
    me, other = e.login("me"), e.login("other")
    a = e.create("Application", {"company": "Mine", "deadline": "9/23 10:00"}, me)
    from ponte.runtime import Ctx
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
    e = engine("spec/hub_ready.ponte")          # 中身（.ai）がまだ無い spec
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
  do    notify me "A"

rule B
  do    notify me "B"

rule C
  when  Job is created
  do    notify me "C"

rule D
  do    move this to filed

rule E
  do    notify me "E"

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
    e.run_rule(e.rules["D"], __import__("ponte.runtime", fromlist=["Ctx"]).Ctx(me, this=j))   # new -> filed は動けない → else E
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
        assert [b["type"] for b in blocks(v, "top")] == ["part", "tabs", "notices", "button"]
        assert [o["icon"] for o in blocks(v, "top")[1]["options"]] == ["clock", "list", "board", "calendar"]
        assert blocks(v, "main")[0]["type"] == "items" and blocks(v, "main")[0]["rows"] == []   # 空 → empty の文とボタン
        assert blocks(v, "main")[0]["empty"]["text"].startswith("3日以内")
        assert blocks(v, "main")[0]["empty"]["button"]["icon"] == "plus"
        assert post("/api/tap", {"user": "me", "button": "add", "on": "Home"})["nav"] == "AddApplication"
        assert blocks(view("AddApplication"), "top")[0]["name"] == "Header"
        assert post("/api/submit", {"user": "me", "input": "AddApplication",
                                    "values": {"company": "Web", "deadline": "2026-09-23T10:00"}})["ok"]
        row = blocks(view(), "main")[0]["rows"][0]
        assert row["title"] == "Web" and row["mark"]["label"] == "下書き"
        assert row["mark"]["color"] == "#F76B15" and row["mark"]["icon"] == "draft"     # 色の match と icon の match は別々に効く
        assert row["lead"]["text"] == "W"
        assert row["sub"]["lines"] == ["9/23 10:00 ・ あと2日"] and row["sub"]["mark"]["value"] == "soon"
        # タブ（画面の状態）で見せ方が変わる
        assert blocks(view(state=json.dumps({"tab": "board"})), "main")[0]["type"] == "board"
        assert blocks(view(state=json.dumps({"tab": "calendar"})), "main")[0]["items"][0]["date"] == "2026-09-23"
        assert blocks(view(state=json.dumps({"menu": "open"})), "over")[0]["type"] == "dialog"
        # 詳しく: flow で動けないボタンは押せない
        r = post("/api/tap", {"user": "me", "button": "card", "on": "Mine", "id": row["id"]})
        assert r["nav"] == "Detail"
        d = blocks(view("Detail", this=row["id"], origin="Mine"), "main")[0]
        assert [(b["label"], bool(b.get("disabled"))) for b in d["buttons"]] == [("提出した", False), ("通過", True), ("不合格", True), ("編集", False), ("消す", False)]
        assert d["buttons"][2]["confirm"] == "不合格にしますか？" and d["buttons"][2]["tone"] == "quiet"
        # 編集: with this で開いた input は、その1件の値が入っている。状態は書き換えられない
        ed = blocks(view("EditApplication", this=row["id"]), "main")[0]
        assert ed["this"] == row["id"] and ed["fields"][0]["value"] == "Web" and ed["fields"][1]["value"] == "2026-09-23T10:00"
        full = {"company": "Web", "deadline": "2026-09-23T10:00"}
        assert post("/api/submit", {"user": "me", "input": "EditApplication", "this": row["id"], "values": {**full, "memo": "一次面接"}})["edited"]
        assert "必須" in post("/api/submit", {"user": "me", "input": "EditApplication", "this": row["id"], "values": {"memo": "x"}})["error"]   # サーバーでも required を守る
        all_ = blocks(view(state=json.dumps({"tab": "all"})), "main")[0]
        assert all_["search"]["fields"] == ["company", "memo"] and [g["value"] for g in all_["groups"]] == ["draft"]
        # board で動かす: flow に無い流れは人の言葉で断る
        bad = post("/api/drag", {"user": "me", "id": row["id"], "to": "passed"})
        assert "「下書き」から「通過」へは動かせません" in bad["error"]
        assert post("/api/drag", {"user": "me", "id": row["id"], "to": "submitted"})["ok"]
        assert blocks(view(), "main")[0]["rows"] == []                  # DueSoon から抜けた
        assert "error" in post("/api/submit", {"user": "me", "input": "AddApplication", "values": {"company": "X", "deadline": "来週"}})
        en = view(lang="en", state=json.dumps({"tab": "all"}))
        assert blocks(en, "main")[0]["groups"][0]["label"] == "Submitted"
        assert blocks(view(lang="en"), "main")[0]["empty"]["text"] == "Nothing due in the next 3 days"   # 引用符の鍵で訳す
    finally:
        httpd.shutdown()


def test_reload_swaps_spec_and_keeps_data(tmp_path):
    """ponte run --reload: 通る書き直しは入れ替え、通らない書き直しは前のまま"""
    import shutil
    from ponte.cli import reload_once
    from ponte.parser import parse_file
    from ponte.server import App
    src = tmp_path / "todo.ponte"
    shutil.copy("spec/todo.ponte", src)
    store = str(tmp_path / "d.jsonl")
    spec = parse_file(str(src))
    eng = Engine(spec, store=store)
    user = eng.login("taro")
    eng.submit(user, "AddTask", {"title": "牛乳"})
    app = App(spec, eng)
    woke = []
    eng.listeners.append(lambda: woke.append(1))
    src.write_text(src.read_text(encoding="utf-8").replace("move this to done", "move this to finished"), encoding="utf-8")
    assert reload_once(str(src), store, app) is False and app.eng is eng
    src.write_text(src.read_text(encoding="utf-8").replace("move this to finished", "move this to done"), encoding="utf-8")
    assert reload_once(str(src), store, app) is True
    assert app.eng is not eng and app.version == 1 and woke
    assert [b.values["title"] for b in app.eng.boxes["Task"].values()] == ["牛乳"]


def test_data_export_and_compact(tmp_path, capsys):
    import csv
    import json as _json
    import shutil
    from ponte.cli import main
    src = tmp_path / "todo.ponte"
    shutil.copy("spec/todo.ponte", src)
    store = str(src) + ".data.jsonl"
    spec = parse_file(str(src))
    eng = Engine(spec, store=store)
    u = eng.login("taro")
    eng.submit(u, "AddTask", {"title": "牛乳"})
    eng.submit(u, "AddTask", {"title": "卵"})
    t = next(b for b in eng.boxes["Task"].values() if b.values["title"] == "卵")
    eng.remove(t, u)
    capsys.readouterr()
    assert main(["data", "export", str(src)]) == 0
    before = _json.loads(capsys.readouterr().out)
    assert main(["data", "export", str(src), "--csv", str(tmp_path / "csv")]) == 0
    rows = list(csv.DictReader(open(tmp_path / "csv" / "Task.csv", encoding="utf-8-sig")))
    assert [r["title"] for r in rows] == [x["title"] for x in before["Task"]]
    assert main(["data", "compact", str(src)]) == 0
    capsys.readouterr()
    main(["data", "export", str(src)])
    assert _json.loads(capsys.readouterr().out) == before           # 詰めても中身は同じ
    eng2 = Engine(parse_file(str(src)), store=store)
    eng2.submit(eng2.login("taro"), "AddTask", {"title": "パン"})   # 番号がぶつからない
    assert len({b.id for b in eng2.boxes["Task"].values()}) == len(before["Task"]) + 1


def test_viewer_is_per_thread():
    """画面のボタンを押せるかは見ている人で決まる。並列の要求で、人が入れ替わらない"""
    import threading
    from ponte.server import App
    spec = parse_file("spec/lend.ponte")
    app = App(spec, Engine(spec))
    app._viewer = "taro"
    seen = []
    t = threading.Thread(target=lambda: seen.append(app._viewer))
    t.start()
    t.join()
    assert seen == ["me"] and app._viewer == "taro"
