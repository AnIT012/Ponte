"""AI を使わずに完結する: action の中身をその場の do に書けば、そのまま動く。"""
from ponte.checker import check
from ponte.examples import run_examples
from ponte.parser import parse

SRC = """action Grade
  in       score number
  out      pass | fail
  example  80 -> pass
  example  59 -> fail
  example  60 -> pass
  never    fail
  else     skip
  do
    answer = match score
      60..  -> pass
      else  -> fail
"""


def test_inline_do_runs_without_ai_or_files():
    spec = parse(SRC)
    assert [f.code for f in check(spec) if f.is_error] == []
    results = run_examples(spec)
    assert results and all(r.ok for r in results), [(r.message) for r in results if not r.ok]


def test_range_matches_numbers_given_as_text():
    from ponte.body import in_range
    assert in_range("80", "60..") and not in_range("59", "60..") and in_range(60.0, "60..")
    assert not in_range(True, "0..")
