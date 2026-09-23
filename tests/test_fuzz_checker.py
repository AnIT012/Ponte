"""壊れた仕様を大量に作って流す。どんな入力でも、Python のエラーで落ちずに「エラーの一覧」か「読めません」になること。
check が通ったものは example も流して、実行エンジンの中の Python エラー（KeyError など）で止まらないこと。"""
import glob
import random

from ponte.checker import check
from ponte.examples import run_examples
from ponte.parser import ParseError, parse

SRCS = [open(p, encoding="utf-8").read() for p in sorted(glob.glob("spec/*.ponte") + glob.glob("tests/cases/*/fixed.ponte"))]
TOKENS = ["this", "me", "->", "|", "[", "]", '"x"', "when", "do", "where", "of", "12:00", "3 days", "tbd", "##", "else",
          "match", "move", "to", "create", "set", "with", "each", "on", "rule A", "thing B", "", "by ai", "never",
          "[a | b]", "status[x |", "found monthday |", "= match this", "count of", "7 days from now", "result", "{title}"]
INTERNAL = ("KeyError", "TypeError", "AttributeError", "IndexError", "ZeroDivisionError")


def mutate(rng, src):
    lines = src.split("\n")
    for _ in range(rng.randint(1, 4)):
        k, op = rng.randrange(len(lines)), rng.random()
        if op < .25:
            del lines[k]
        elif op < .5:
            w = lines[k].split(" ")
            w[rng.randrange(len(w))] = rng.choice(TOKENS)
            lines[k] = " ".join(w)
        elif op < .7:
            lines[k] = " " * rng.choice([0, 1, 2, 3, 4, 6]) + lines[k].lstrip()
        elif op < .85:
            lines.insert(k, lines[rng.randrange(len(lines))])
        else:
            lines[k] = lines[k][:rng.randrange(len(lines[k]) + 1)]
    return "\n".join(lines)


def test_broken_specs_never_crash():
    rng = random.Random(20260923)
    for i in range(400):
        src = mutate(rng, rng.choice(SRCS))
        try:
            spec = parse(src)
        except ParseError:
            continue
        findings = check(spec)            # ここで落ちたらテストが落ちる
        if not [f for f in findings if f.is_error]:
            for r in run_examples(spec):
                assert not (not r.ok and r.message.split(":")[0] in INTERNAL), f"{i}: {r.message}\n{src}"


def test_broken_requests_get_a_clean_answer():
    """画面の API に変な形のリクエストを送っても、接続が切れたり 500 になったりせず、JSON のエラーが返る"""
    import http.client
    import json
    import threading

    from ponte.parser import parse_file
    from ponte.runtime import Engine
    from ponte.server import serve
    spec = parse_file("spec/lend.ponte")
    httpd = serve(spec, Engine(spec), port=0, ticker=False)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    rng = random.Random(7)
    vals = [None, "", 0, 1.5, "x", [], {}, {"a": 1}, "Item-1", "borrow-button", "Item", "free", True]
    keys = ["user", "button", "on", "id", "input", "values", "this", "text", "to", "lang", "year_answers"]
    try:
        for _ in range(300):
            path = rng.choice(["/api/tap", "/api/undo", "/api/drag", "/api/submit", "/api/says", "/api/nope"])
            if rng.random() < .15:
                body = rng.choice([b"{", b"[]", b"null", b"\xff\xfe", b"1"])
            else:
                body = json.dumps({k: rng.choice(vals) for k in rng.sample(keys, rng.randint(0, 6))}).encode()
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            c.request("POST", path, body=body, headers={"content-type": "application/json"})
            r = c.getresponse()
            assert r.status < 500, (path, body)
            json.loads(r.read())
        for q in ["/api/view?scene=Nope", "/api/view?state={", "/api/view?state=[]"]:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            c.request("GET", q)
            r = c.getresponse()
            assert r.status < 500, q
            json.loads(r.read())
    finally:
        httpd.shutdown()
