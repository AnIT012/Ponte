"""AIに中身を書かせるループのテスト。AIの代わりに、決まった返事を順に返す関数を使う。"""
import json
import shutil
from datetime import datetime

import pytest

from lang import fill as F
from lang.parser import parse_file
from lang.runtime import Engine

GOOD = open("experiment/ai_replies/ExtractDeadline/1.md", encoding="utf-8").read()
SHAPE = GOOD[GOOD.index("shape Deadline"):GOOD.rindex("```")]

BAD_SYNTAX = "```lang\ndo\n  text normalize mail\n```"
BAD_NESTED = """```lang
do
  hits = find all Deadline in mail
  deadline = match count of hits
               1    -> match first of hits
               else -> missing

""" + SHAPE + "```"
BAD_WRONG = """```lang
do
  hits = find all Deadline in mail
  deadline = match count of hits
               0    -> missing
               else -> found monthday of first of hits

""" + SHAPE + "```"
BAD_YEAR = """```lang
do
  hits = find all Deadline in mail
  deadline = match count of hits
               1    -> found join split "2026 10/15 12:00" by "," by ","
               else -> missing

""" + SHAPE + "```"


def scripted(*replies):
    seen = []

    def ai(messages):
        seen.append([m["content"] for m in messages])
        return replies[len(seen) - 1]
    ai.seen = seen
    return ai


@pytest.fixture
def spec(tmp_path):
    p = tmp_path / "hub.lang"
    shutil.copy("spec/hub_app.lang", p)
    return parse_file(str(p))


def test_loop_feeds_errors_back_until_it_passes(spec):
    a = spec.find("action", "ExtractDeadline")
    ai = scripted(BAD_SYNTAX, BAD_NESTED, BAD_WRONG, GOOD)
    r = F.fill_action(spec, a, ai, tries=5)
    assert r.ok and r.tries == 4
    assert any("do に書けるのは" in p for p in r.history[0])
    assert any("入れ子" in p for p in r.history[1])
    assert any("9/24 23:59 または 9/30 23:59" in p for p in r.history[2])   # 2つ見つかったのに found にした
    assert r.history[3] == []
    # 2回目以降のプロンプトには、前の回の問題がそのまま入っている
    assert "入れ子" in ai.seen[2][-1]
    assert open(r.path, encoding="utf-8").read().count("shape Deadline") == 1


def test_loop_gives_up_after_tries(spec):
    r = F.fill_action(spec, spec.find("action", "ExtractDeadline"), scripted(BAD_WRONG, BAD_WRONG), tries=2)
    assert not r.ok and r.tries == 2 and r.path is None


def test_never_guess_the_year_is_checked(spec):
    v = F.verify(spec, spec.find("action", "ExtractDeadline"), F.extract_code(BAD_YEAR))
    assert any(p.startswith("never guess the year") for p in v.problems)


def test_engine_uses_the_filled_body(spec):
    F.fill_action(spec, spec.find("action", "ExtractDeadline"), scripted(GOOD))
    e = Engine(parse_file(spec.path), clock=lambda: datetime(2026, 9, 21, 9, 0))
    assert "ExtractDeadline" in e.bodies
    e.gives("Gmail", "new message", "ES締切：１０／１５（木）１２：００まで")
    assert e.notifications == []                           # 見つかった → 逃げ道には行かない
    e.gives("Gmail", "new message", "来週中にご提出ください")
    assert "決められませんでした" in e.notifications[-1]["text"]   # missing → else ask user


def test_human_can_edit_the_body_and_test_catches_it(spec):
    from lang.examples import run_action_examples
    r = F.fill_action(spec, spec.find("action", "ExtractDeadline"), scripted(GOOD))
    src = open(r.path, encoding="utf-8").read().replace("1    -> one", "1    -> many")
    open(r.path, "w", encoding="utf-8").write(src)
    bad = [x for x in run_action_examples(parse_file(spec.path)) if not x.ok]
    assert len(bad) == 2                                   # 見つかるはずの2つが missing になる


def test_http_request_shape(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    sent = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"stop_reason": "end_turn", "content": [{"type": "text", "text": "```lang\ndo\n```"}]}).encode()

    def fake_urlopen(req, timeout):
        sent["headers"] = {k.lower(): v for k, v in req.header_items()}
        sent["body"] = json.loads(req.data)
        return Resp()
    monkeypatch.setattr(F.urllib.request, "urlopen", fake_urlopen)
    out = F.AnthropicHTTP()([{"role": "user", "content": "hi"}])
    assert out.startswith("```lang")
    assert sent["body"]["model"] == "claude-opus-5" and sent["body"]["fallbacks"] == "default"
    assert sent["headers"]["x-api-key"] == "test-key"
    assert sent["headers"]["anthropic-beta"] == "server-side-fallback-2026-07-01"
    assert "thinking" not in sent["body"] and "temperature" not in sent["body"]


def test_answer_line_may_repeat_the_out_form(spec):
    """実験の B3: 答えの行に out の形 [found monthday | missing] を書いても通る"""
    code = F.extract_code(open("experiment/v2/runs/B3/reply.md", encoding="utf-8").read())
    assert F.verify(spec, spec.find("action", "ExtractDeadline"), code).ok


def test_never_depend_on_width_catches_missing_normalize(spec):
    """実験の B5: normalize を忘れると、例は通っても never depend on width で止まる"""
    code = F.extract_code(open("experiment/v2/runs/B5/reply.md", encoding="utf-8").read())
    v = F.verify(spec, spec.find("action", "ExtractDeadline"), code)
    assert not v.ok and all(p.startswith("never depend on width") for p in v.problems)
    assert F.to_fullwidth("9/24 23:59") == "９／２４\u3000２３：５９".replace("\u3000", " ")


def test_reply_that_repeats_the_contract_is_read(spec):
    """実験2回目の B4: 契約まで書き写して、do と shape を中に字下げした返事も読める（中身は変えない）"""
    code = F.extract_code(open("experiment/v2/runs2/B4/reply.md", encoding="utf-8").read())
    assert F.verify(spec, spec.find("action", "ExtractDeadline"), code).ok


def test_habit_hints_teach_this_language():
    """他の言語のクセで書いたら、この言語での書き方を返す。同じ間違いは1回だけ"""
    from lang.fill import verify
    spec = parse_file("spec/hub_app.lang")
    a = spec.find("action", "ExtractDeadline")
    cases = {
        "do\n  x = trim mail\n  if x == 1:\n    y = x\n": "match 式",
        "do\n  return missing\n": "答えは「他のどの行からも使われていない行」",
        'do\n  hits = re.findall(r"\\d+", mail)\n': "shape",
        "do\n  a = len(mail)\n": "count of X",
        "do\n  a = bogus mail\n": "使える道具",
    }
    for code, hint in cases.items():
        probs = verify(spec, a, code).problems
        assert hint in probs[0], (code, probs[0])
    probs = verify(spec, a, "do\n  a = bogus mail\n").problems
    assert sum("bogus" in p for p in probs if p.startswith("example")) == 1
