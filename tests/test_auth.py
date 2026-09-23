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
    return r.status, dict((k.lower(), v) for k, v in r.getheaders()), r.read().decode()


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
    assert req(port, "GET", "/logout", headers={"cookie": cookie})[0] == 303
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
    assert st == 200 and 'taro ・ <a href="/logout">' in body


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
