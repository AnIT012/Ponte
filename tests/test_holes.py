"""ponte test の穴さがし：example で確かめていない所を出す。"""
from ponte.examples import holes, run_examples
from ponte.parser import parse, parse_file

SRC = '''
thing Task
  title text
  status[open | done | dropped]

flow Task.status
  open -> done | dropped

who
  user can change Task

action Classify
  in   t text
  out  urgent | normal | spam
  example "今すぐ" -> urgent
  example "あとで" -> normal

rule Finish
  when  user taps done-button on Task
  do    move this to done
  example
    given Task
      title   "a"
      status  open
    taps done-button on Task
      title "a"
    expect Task is done
      title "a"

rule Drop
  when  user taps drop-button on Task
  do    move this to dropped
'''


def msgs(src):
    s = parse(src)
    return [h.message for h in holes(s, run_examples(s))]


def test_holes_found():
    m = msgs(SRC)
    assert "rule Drop: when があるのに example がありません" in m
    assert "flow Task.status: open -> dropped をどの example も通っていません" in m
    assert "action Classify: 答えが spam になる example がありません" in m
    assert all(r.ok for r in run_examples(parse(SRC)))
    assert not any("open -> done" in x for x in m)       # Finish の example が通っている


def test_full_app_has_no_holes():
    s = parse_file("spec/hub_app.ponte")
    assert holes(s, run_examples(s)) == []
