"""ponte run --login: 合言葉のログイン。cookie の鍵だけを信じ、?user= では誰にもなれない。"""
import http.client
import json
import threading
from urllib.parse import urlencode

import pytest

from ponte.auth import Users
from ponte.cli import main
from ponte.parser import parse_file
from ponte.runtime import Engine
from ponte.server import Auth, serve

SPEC = "spec/todo.ponte"


@pytest.fixture
def site(tmp_path):
    users = Users(str(tmp_path / "u.json"))
    users.add("taro", "correct-horse")
    spec = parse_file(SPEC)
    httpd = serve(spec, Engine(spec, store=str(tmp_path / "d.jsonl")), port=0, ticker=False, auth=Auth(users, signup=True))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1], users
    httpd.shutdown()


def req(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    raw = r.read()
    return r.status, dict((k.lower(), v) for k, v in r.getheaders()), raw.decode("utf-8", "replace")


def login(port, name, pw, path="/login"):
    return req(port, "POST", path, urlencode({"name": name, "password": pw}),
               {"content-type": "application/x-www-form-urlencoded"})


def test_without_login_everything_is_closed(site):
    port, _ = site
    assert req(port, "GET", "/")[0:2][0] == 303
    st, _, body = req(port, "GET", "/api/view?user=taro")
    assert st == 401 and json.loads(body)["login"] is True
    assert req(port, "POST", "/api/tap", json.dumps({"user": "taro"}), {"content-type": "application/json"})[0] == 401


def test_login_and_cookie_is_the_only_identity(site):
    port, _ = site
    st, h, _ = login(port, "taro", "wrong-password")
    assert st == 401 and "set-cookie" not in h
    st, h, _ = login(port, "taro", "correct-horse")
    assert st == 303
    cookie = h["set-cookie"].split(";")[0]
    assert "HttpOnly" in h["set-cookie"] and "SameSite=Lax" in h["set-cookie"]
    st, _, body = req(port, "GET", "/api/view?user=someone-else", headers={"cookie": cookie})
    assert st == 200
    # フォームからの POST（json でない）は、ログインしていても受け付けない
    assert req(port, "POST", "/api/tap", "a=b", {"cookie": cookie, "content-type": "application/x-www-form-urlencoded"})[0] == 415
    assert req(port, "GET", "/logout", headers={"cookie": cookie})[0] == 405      # GET では切れない（よそのリンクで切らせない）
    assert req(port, "GET", "/api/view", headers={"cookie": cookie})[0] == 200
    assert req(port, "POST", "/logout", "", {"cookie": cookie})[0] == 303
    assert req(port, "GET", "/api/view", headers={"cookie": cookie})[0] == 401


def test_signup_rules(site):
    port, users = site
    assert login(port, "hanako", "short", "/signup")[0] == 401
    assert login(port, "taro", "another-pass", "/signup")[0] == 401          # 取られた名前
    assert login(port, "hanako", "long-enough", "/signup")[0] == 303
    assert users.verify("hanako", "long-enough") and not users.verify("hanako", "nope-nope")


def test_too_many_failures_are_slowed(site):
    port, _ = site
    for _ in range(10):
        login(port, "taro", "wrong-password")
    st, _, body = login(port, "taro", "correct-horse")
    assert st == 401 and "少し待って" in body


def test_password_is_not_stored(tmp_path):
    u = Users(str(tmp_path / "u.json"))
    u.add("a", "secret-words")
    assert "secret-words" not in (tmp_path / "u.json").read_text()
    assert Users(str(tmp_path / "u.json")).verify("a", "secret-words")


def test_public_host_needs_login(capsys):
    assert main(["run", SPEC, "--host", "0.0.0.0"]) == 1
    assert "--login" in capsys.readouterr().out


def test_user_command(tmp_path, monkeypatch, capsys):
    spec = tmp_path / "a.ponte"
    spec.write_text(open(SPEC, encoding="utf-8").read(), encoding="utf-8")
    monkeypatch.setenv("PONTE_PASSWORD", "twelve-chars")
    assert main(["user", "add", str(spec), "taro"]) == 0
    assert Users(str(spec) + ".users.json").verify("taro", "twelve-chars")
    assert main(["user", "remove", str(spec), "taro"]) == 0


def test_page_shows_who_is_logged_in(site):
    port, _ = site
    _, h, _ = login(port, "taro", "correct-horse")
    cookie = h["set-cookie"].split(";")[0]
    st, _, body = req(port, "GET", "/", headers={"cookie": cookie})
    assert st == 200 and 'taro ・ <form method="post" action="/logout"' in body


def test_lang_in_url_cannot_inject(tmp_path):
    import threading as _t
    spec = parse_file(SPEC)
    httpd = serve(spec, Engine(spec), port=0, ticker=False)
    _t.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        st, _, body = req(httpd.server_address[1], "GET", '/?lang=%22%3Balert(1)%3B%2F%2F%3C%2Fscript%3E')
        assert st == 200 and "alert(1)" not in body
    finally:
        httpd.shutdown()


def test_security_headers(site):
    port, _ = site
    _, h, _ = req(port, "GET", "/login")
    assert h["x-frame-options"] == "DENY" and h["x-content-type-options"] == "nosniff"


PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def test_images_are_checked_stored_and_served_by_who(tmp_path):
    import base64
    import threading as _t
    spec = parse_file("spec/lend.ponte")
    eng = Engine(spec, store=str(tmp_path / "d.jsonl"))
    eng.set_role("boss", "admin")
    httpd = serve(spec, eng, port=0, ticker=False)
    _t.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    post = lambda body: req(port, "POST", "/api/submit", json.dumps(body), {"content-type": "application/json"})
    try:
        st, _, body = post({"user": "boss", "input": "AddItem", "values": {"name": "カメラ", "photo": PNG}})
        assert st == 200, body
        item = next(b for b in eng.boxes["Item"].values() if b.values["name"] == "カメラ")
        v = item.values["photo"]
        assert v.startswith("file:") and v.endswith(".png") and (tmp_path / "d.jsonl.files" / v[5:]).exists()
        st, h, _ = req(port, "GET", "/files/" + v[5:] + "?user=taro")
        assert st == 200 and h["content-type"] == "image/png"
        fake = "data:image/png;base64," + base64.b64encode(b"<script>alert(1)</script>").decode()
        assert post({"user": "boss", "input": "AddItem", "values": {"name": "偽物", "photo": fake}})[0] == 400
        assert post({"user": "boss", "input": "AddItem", "values": {"name": "借用", "photo": v}})[0] == 400   # 他の画像を名前で指せない
        assert req(port, "GET", "/files/" + "0" * 32 + ".png")[0] == 404
        assert req(port, "GET", "/files/../../etc/passwd")[0] == 404
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)      # 大きすぎる中身は、読む前に断る
        c.putrequest("POST", "/api/submit")
        c.putheader("content-type", "application/json")
        c.putheader("content-length", str(9 * 1024 * 1024))
        c.endheaders()
        assert c.getresponse().status == 413
    finally:
        httpd.shutdown()


def test_removed_user_is_logged_out_and_signups_are_limited(site):
    port, users = site
    _, h, _ = login(port, "taro", "correct-horse")
    cookie = h["set-cookie"].split(";")[0]
    assert req(port, "GET", "/api/view", headers={"cookie": cookie})[0] == 200
    other = Users(users.path)                        # 別のところ（ponte user remove）で消す
    other.data.pop("taro")
    import os as _os, time as _time
    _time.sleep(0.01)
    other._save()
    _os.utime(users.path, None)
    assert req(port, "GET", "/api/view", headers={"cookie": cookie})[0] == 401
    codes = [login(port, f"u{i}", "long-enough", "/signup")[0] for i in range(7)]
    assert codes[:5] == [303] * 5 and codes[5] == 401


def test_review_fixes(site, tmp_path):
    """見直しで見つかった穴: 登録で上書き・データのある名前の横取り・よそのページからのログイン・入力に無い項目・深い JSON"""
    port, users = site
    import pytest as _pytest
    with _pytest.raises(ValueError):
        users.add("taro", "another-password")                   # 画面の登録では上書きしない
    assert users.verify("taro", "correct-horse")
    st, _, body = req(port, "POST", "/login", urlencode({"name": "taro", "password": "correct-horse"}),
                      {"content-type": "application/x-www-form-urlencoded", "origin": "http://evil.example"})
    assert st == 403
    _, h, _ = login(port, "taro", "correct-horse")
    cookie = h["set-cookie"].split(";")[0]
    j = {"cookie": cookie, "content-type": "application/json"}
    st, _, body = req(port, "POST", "/api/submit", json.dumps({"input": "AddTask", "values": {"title": "x", "owner": "User-9"}}), j)
    assert st == 400 and "この入力にはありません" in body
    assert req(port, "POST", "/api/submit", b"[" * 100000, j)[0] == 400


def test_signup_cannot_take_a_name_that_already_has_data(tmp_path):
    import threading as _t
    users = Users(str(tmp_path / "u.json"))
    spec = parse_file("spec/lend.ponte")
    eng = Engine(spec)
    eng.set_role("boss", "admin")                           # ponte role で先に管理者にした名前
    httpd = serve(spec, eng, port=0, ticker=False, auth=Auth(users, signup=True))
    _t.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        st, _, body = login(httpd.server_address[1], "boss", "long-enough", "/signup")
        assert st == 401 and "使われています" in body
    finally:
        httpd.shutdown()
