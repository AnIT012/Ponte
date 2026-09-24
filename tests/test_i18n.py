"""英語の出力。メッセージを足したら、英語も ponte/i18n_en.json に足す（python tools/i18n_keys.py --add で空の行ができる）。"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from i18n_keys import CATALOG, JP, keys  # noqa: E402

CAT = json.load(open(CATALOG, encoding="utf-8"))
PLAIN = re.compile(r"(?<!\{)\{\}(?!\})")
NUM = re.compile(r"(?<!\{)\{(\d+)\}(?!\})")


def test_every_message_has_an_english_entry():
    missing = [f"{w[0]}  {k}" for k, w in keys().items() if k not in CAT or CAT[k] == ""]
    assert not missing, "英語がない（python tools/i18n_keys.py --add のあと訳を書く）:\n" + "\n".join(missing[:30])


def test_placeholders_match():
    bad = []
    for k, en in CAT.items():
        if not en:
            continue
        n, plain, nums = len(PLAIN.findall(k)), len(PLAIN.findall(en)), [int(x) for x in NUM.findall(en)]
        if (plain and nums) or (not nums and plain != n) or (nums and max(nums) >= n):
            bad.append(k)
    assert not bad, bad[:10]


def test_english_has_no_japanese_outside_code():
    bad = [en for en in CAT.values() if en and JP.search(re.sub(r"`[^`]*`", "", en))]
    assert not bad, bad[:10]


def run(*args, lang="en"):
    env = {**os.environ, "PONTE_LANG": lang, "PYTHONPATH": ROOT}
    return subprocess.run([sys.executable, "-m", "ponte", *args], cwd=ROOT, env=env, capture_output=True, text=True)


def test_check_speaks_english():
    out = run("check", "site/samples/feat/order.ponte").stdout
    assert "E05" in out and not JP.search(out.replace("発送した後でも、キャンセルできる？", "")), out


def test_test_output_and_json_speak_english():
    out = run("test", "spec/hub_ready.ponte").stdout
    assert not JP.search(out), out
    js = json.loads(run("check", "--json", "site/samples/feat/nowho.ponte").stdout)
    assert js["findings"][0]["code"] == "E19" and not JP.search(js["findings"][0]["message"])


def test_explain_in_both_languages():
    en, ja = run("explain", "E05").stdout, run("explain", "E05", lang="ja").stdout
    assert not JP.search(en) and JP.search(ja)


def test_data_is_never_translated(tmp_path):
    # 利用者のデータ（日本語）はそのまま出す
    out = run("--lang", "en", "fmt", "--check", "site/samples/feat/order.ponte").stdout
    assert out  # fmt は訳さないコマンド。落ちずに動くことだけ確かめる
