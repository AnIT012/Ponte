"""ponte/skeleton.py の「必須の部品」は、本当に必須（抜くと check がエラーを出す）。"""
import pytest

from ponte.checker import check
from ponte.parser import parse
from ponte.skeleton import REQUIRED, lines_after, snippet

BASE = """thing Task
  title   text
  score   number
  status  [todo | done]

flow Task.status
  todo -> done

who
  user  can see     Task
  user  can change  Task
"""
FULL = {
    "rule": "rule Finish\n  when  user taps done-button on Task\n  do    move this to done\n",
    "action": 'action A\n  in       t text\n  out      yes | no\n  example  "a" -> yes\n  example  "b" -> no\n  else     skip\n',
    "list": "list L\n  of     Task\n  where  status is todo\n",
    "match": "match Task.status to color\n  todo -> red\n  else -> blue\n",
    "model": "model M\n  learn    status from Task\n  using    score\n  require  accuracy at least 80%\n  else     skip\n",
    "job": "job J\n  run      python train.py\n",
}


def errors(src):
    return [f.code for f in check(parse(BASE + "\n" + src)) if f.is_error]


@pytest.mark.parametrize("word", sorted(REQUIRED))
def test_full_form_passes(word):
    assert errors(FULL[word]) == []


@pytest.mark.parametrize("word,i", [(w, i) for w in sorted(REQUIRED) for i in range(len(REQUIRED[w]))])
def test_each_listed_part_is_required(word, i):
    part = REQUIRED[word][i]
    lines = FULL[word].splitlines()
    idx = [k for k, l in enumerate(lines) if l.strip().startswith(part.split()[0] + " ") or l.strip() == part][0 if part != "example" else i - REQUIRED[word].index("example")]
    src = "\n".join(lines[:idx] + lines[idx + 1:]) + "\n"
    assert errors(src), f"{word}: removing {part!r} is not an error"


def test_editor_helpers():
    assert lines_after("rule Finish") == ["  when ", "  do "]
    assert lines_after("thing Task") == [] and lines_after("  rule x") == []
    assert snippet("list") == "list $1\n  of $2"
    assert snippet("thing") is None
