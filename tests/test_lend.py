"""2つ目のアプリ（備品かしだし）で足した言語の道具。"""
from datetime import datetime

from lang.checker import check
from lang.examples import holes, run_examples
from lang.parser import parse_file
from lang.runtime import Engine

SPEC = parse_file("spec/lend.lang")


def eng_at(now=datetime(2026, 9, 21, 10, 0)):
    return Engine(SPEC, clock=lambda: now, parallel=False)


def test_passes_check_and_has_no_holes():
    assert [f for f in check(SPEC) if f.is_error] == []
    res = run_examples(SPEC)
    assert all(r.ok for r in res), [r for r in res if not r.ok]
    assert holes(SPEC, res) == []


def test_create_with_values_and_move_of_this():
    e = eng_at()
    me = e.login("me")
    cam = e.create("Item", {"name": "カメラ"}, me, check=False)
    e.tap(me, "borrow-button", "Item", cam.id)
    [loan] = e.all("Loan")
    assert loan.values["item"] == cam.id and loan.values["borrower"] == me.id
    assert loan.values["due"] == "2026/9/28 10:00"          # 7 days from now。年まで書く
    assert cam.values["status"] == "lent"                   # move item of this to lent


def test_rule_where_skips_quietly():
    e = eng_at()
    me = e.login("me")
    cam = e.create("Item", {"name": "カメラ", "status": "lent"}, me, check=False)
    e.tap(me, "borrow-button", "Item", cam.id)
    assert e.all("Loan") == [] and e.notifications == []


def test_button_disabled_by_rule_where():
    from lang.server import App
    e = eng_at()
    me = e.login("me")
    cam = e.create("Item", {"name": "カメラ", "status": "lent"}, me, check=False)
    app = App(SPEC, e)
    app._viewer = "me"
    assert not app.can_press(cam, "borrow-button", "Item")
    assert not app.can_press(cam, "fixed-button", "Item")
    assert app.can_press(cam, "broken-button", "Item")


def test_notify_shows_label_of_referenced_box():
    e = eng_at(datetime(2026, 9, 21, 9, 0))
    me = e.login("me")
    mic = e.create("Item", {"name": "マイク", "status": "lent"}, me, fire=False, check=False)
    e.create("Loan", {"item": mic.id, "due": "9/20 18:00"}, me, fire=False)
    e.tick()
    assert [n["text"] for n in e.notifications] == ["マイク の返却日を過ぎています"]


def test_undo_not_offered_when_tap_changed_other_boxes():
    """借りる = 貸し出しを作る＋備品を動かす。半分だけ戻すと食い違うので、取り消しは出さない"""
    import json
    import threading
    import urllib.request
    from lang.server import serve
    e = eng_at()
    httpd = serve(SPEC, e, port=0, ticker=False)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def post(path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{httpd.server_address[1]}{path}", json.dumps(body).encode(),
                                     {"content-type": "application/json"})
        return json.loads(op.open(req).read())
    try:
        me = e.login("me")
        cam = e.create("Item", {"name": "カメラ"}, me, check=False)
        assert post("/api/tap", {"user": "me", "button": "borrow-button", "on": "Items", "id": cam.id})["undo"] is None
        light = e.create("Item", {"name": "ライト"}, me, check=False)
        assert post("/api/tap", {"user": "me", "button": "broken-button", "on": "Items", "id": light.id})["undo"] == light.id
    finally:
        httpd.shutdown()


def test_roles_come_from_user_role(tmp_path):
    from lang.cli import main
    store = str(tmp_path / "d.jsonl")
    assert main(["role", "spec/lend.lang", "taro", "admin", "--data", store]) == 0
    assert main(["role", "spec/lend.lang", "taro", "king", "--data", store]) == 1       # 無い役割
    e = Engine(SPEC, store=store, parallel=False)
    taro, hana = e.login("taro"), e.login("hanako")
    assert "admin" in taro.roles and "admin" not in hana.roles
    e.create("Item", {"name": "カメラ"}, taro)                   # admin だけが備品を足せる
    try:
        e.create("Item", {"name": "マイク"}, hana)
        raise AssertionError("member が備品を足せてしまった")
    except Exception as err:
        assert "作れません" in str(err)
    hbox = e.boxes["User"][hana.id]
    e.tap(taro, "admin-button", "User", hbox.id)                  # 管理者が増やす
    assert "admin" in e.login("hanako").roles


def test_add_button_only_for_those_who_can_create(tmp_path):
    from lang.server import App
    store = str(tmp_path / "d.jsonl")
    e = Engine(SPEC, store=store, parallel=False)
    e.set_role("taro", "admin")
    app = App(SPEC, e)

    def buttons(user):
        v = app.view("Home", e.login(user), {}, None, None, "ja")
        return [b.get("id") for s in v["slots"] for b in s["blocks"] if b.get("type") == "button"]
    assert "add" in buttons("taro")
    assert "add" not in buttons("hanako")
