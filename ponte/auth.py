"""本当のログイン（`ponte run --login`）。標準ライブラリだけ。

- 合言葉は hashlib.scrypt で塩を入れて残す（<spec>.users.json。合言葉そのものは残さない）
- ログインしたら、ランダムな鍵を HttpOnly の cookie で渡す。鍵はメモリにだけ持つ（止めたらログインし直し）
- 名前は who の `me` になる。役割は今まで通り thing User の role[...]
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time

_N, _R, _P = 2 ** 14, 8, 1
SESSION_SECONDS = 14 * 24 * 3600
COOKIE = "ponte_session"


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=32)


class Users:
    def __init__(self, path: str):
        self.path = path
        self.lock = threading.Lock()
        self.data: dict[str, dict] = {}
        self._mtime = None
        self._load()

    def _load(self) -> None:
        """ファイルが書き換わっていたら読み直す（動かしている間に ponte user add / remove しても効く）"""
        try:
            mt = os.path.getmtime(self.path)
        except OSError:
            return
        if mt != self._mtime:
            with open(self.path, encoding="utf-8") as f:
                self.data = json.load(f)
            self._mtime = mt

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        try:
            self._mtime = os.path.getmtime(self.path)
        except OSError:
            pass

    def add(self, name: str, password: str, overwrite: bool = False) -> None:
        """人を足す。overwrite は ponte user add（合言葉を変える）の時だけ。画面の登録では、いる人を上書きしない"""
        name = name.strip()
        if not name or len(name) > 64:
            raise ValueError("名前は1〜64文字にしてください")
        if len(password) < 8:
            raise ValueError("合言葉は8文字以上にしてください")
        salt = secrets.token_bytes(16)
        h = _hash(password, salt).hex()
        with self.lock:
            self._load()                          # 別のところ（ponte user add）で足した人を消さない
            if name in self.data and not overwrite:
                raise ValueError("その名前はもう使われています")
            self.data[name] = {"salt": salt.hex(), "hash": h}
            self._save()

    def exists(self, name: str) -> bool:
        self._load()
        return name in self.data

    def verify(self, name: str, password: str) -> bool:
        self._load()
        u = self.data.get(name)
        if u is None:
            _hash(password, b"\0" * 16)          # 無い名前でも同じだけ時間をかける（名前があるかを漏らさない）
            return False
        return hmac.compare_digest(_hash(password, bytes.fromhex(u["salt"])).hex(), u["hash"])


class Sessions:
    def __init__(self):
        self.lock = threading.Lock()
        self.data: dict[str, tuple[str, float]] = {}

    def start(self, name: str) -> str:
        token = secrets.token_urlsafe(32)
        with self.lock:
            self.data[token] = (name, time.time() + SESSION_SECONDS)
        return token

    def who(self, token: str | None) -> str | None:
        if not token:
            return None
        with self.lock:
            v = self.data.get(token)
            if v is None:
                return None
            if v[1] < time.time():
                del self.data[token]
                return None
            return v[0]

    def end(self, token: str | None) -> None:
        with self.lock:
            self.data.pop(token or "", None)


def cookie_token(header: str | None) -> str | None:
    for part in (header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == COOKIE:
            return v
    return None


LOGIN_PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f7f7f5;--fg:#1f2328;--sub:#6b7280;--card:#fff;--line:#e5e7eb;--accent:#4f46e5;--err:#b42318}
@media (prefers-color-scheme: dark){:root{--bg:#16171a;--fg:#e6e6e6;--sub:#9aa0a6;--card:#202226;--line:#2f3237;--accent:#8b87ff;--err:#ff8a80}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,sans-serif;padding:16px}
form{width:100%;max-width:340px;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:28px 24px;display:grid;gap:14px}
h1{margin:0 0 4px;font-size:20px}
label{display:grid;gap:4px;font-size:14px;color:var(--sub)}
input{font:inherit;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:transparent;color:var(--fg)}
input:focus{outline:2px solid var(--accent);outline-offset:1px}
button{font:inherit;font-weight:600;padding:11px;border:0;border-radius:10px;background:var(--accent);color:#fff;cursor:pointer}
.err{color:var(--err);font-size:14px;min-height:1.2em;margin:0}
.alt{font-size:14px;color:var(--sub);text-align:center;margin:0}
.alt a{color:var(--accent)}
</style></head><body>
<form method="post" action="__ACTION__">
  <h1>__HEADING__</h1>
  <label>名前<input name="name" autocomplete="username" required maxlength="64" autofocus></label>
  <label>合言葉<input name="password" type="password" autocomplete="__AUTOCOMPLETE__" required minlength="8"></label>
  <p class="err" role="alert">__ERROR__</p>
  <button type="submit">__BUTTON__</button>
  __ALT__
</form>
</body></html>
"""


def login_page(title: str, error: str = "", signup: bool = False, allow_signup: bool = False) -> str:
    import html
    alt = ""
    if allow_signup:
        alt = ('<p class="alt">もう登録している方は <a href="/login">ログイン</a></p>' if signup
               else '<p class="alt">はじめての方は <a href="/signup">登録</a></p>')
    return (LOGIN_PAGE.replace("__TITLE__", html.escape(title)).replace("__ACTION__", "/signup" if signup else "/login")
            .replace("__HEADING__", "登録" if signup else "ログイン").replace("__BUTTON__", "登録する" if signup else "ログイン")
            .replace("__AUTOCOMPLETE__", "new-password" if signup else "current-password")
            .replace("__ERROR__", html.escape(error)).replace("__ALT__", alt))
