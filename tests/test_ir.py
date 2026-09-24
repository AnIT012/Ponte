"""IR: check を通った仕様を JSON にして、何も失わずに戻せる。共通テストは基準の実装で全部通り、壊れた実装は落とす。"""
import glob
import json

import pytest

from ponte.examples import run_examples
from ponte.ir import NotChecked, from_ir, run_case, to_ir
from ponte.parser import parse, parse_file

SPECS = [p for p in sorted(glob.glob("spec/*.ponte") + glob.glob("ponte/templates/*.ponte")) if not p.endswith("hub.ponte")]


@pytest.mark.parametrize("path", SPECS)
def test_round_trip_keeps_behavior(path):
    spec = parse_file(path)
    ir = json.loads(json.dumps(to_ir(spec), ensure_ascii=False))       # 本当に JSON を通す
    back = from_ir(ir)
    assert [(r.rule, r.ok) for r in run_examples(spec)] == [(r.rule, r.ok) for r in run_examples(back)]


@pytest.mark.parametrize("path", SPECS)
def test_every_shared_case_passes_on_the_reference(path):
    ir = to_ir(parse_file(path))
    spec = from_ir(ir)
    bad = [(c.get("rule") or c.get("action"), r.message) for c in ir["cases"] for r in [run_case(spec, c)] if not r.ok]
    assert not bad


def test_a_wrong_implementation_fails_the_cases():
    ir = to_ir(parse_file("spec/kakeibo.ponte"))
    ir["bodies"]["FindYen"] = ir["bodies"]["FindYen"].replace("one  -> found amount", "one  -> missing")
    spec = from_ir(ir)
    results = [run_case(spec, c) for c in ir["cases"] if c.get("action") == "FindYen"]
    assert any(not r.ok for r in results)


def test_rule_cases_catch_a_changed_rule():
    ir = to_ir(parse_file("spec/todo.ponte"))
    ir["source"] = ir["source"].replace("do     move this to done", "do     move this to todo")
    spec = from_ir(ir)
    assert any(not run_case(spec, c).ok for c in ir["cases"] if c.get("rule") == "Finish")


def test_undecided_spec_has_no_ir():
    with pytest.raises(NotChecked):
        to_ir(parse("thing A\n  x  text\n\ntbd  まだ\n"))


def test_ir_has_the_readable_parts():
    ir = to_ir(parse_file("spec/todo.ponte"))
    assert ir["ponte_ir"] == 1 and ir["things"]["Task"]["fields"][0]["name"] == "title"
    assert ["todo", "done"] in ir["flows"]["Task.status"]["edges"]
    assert {"role": "user", "can": "see", "thing": "Task"}.items() <= ir["who"][0].items()
    assert ir["cases"] and ir["cases"][0]["steps"][0]["kind"] in ("given", "at")


def test_cli_ir_and_conform_are_quick(tmp_path):
    """IR はデータなので訳さない（長い行を訳そうとして止まったことがある）。conform は基準の実装で全部通る"""
    import os
    import subprocess
    import sys
    env = {**os.environ, "PONTE_LANG": "en"}
    out = tmp_path / "todo.ir.json"
    r = subprocess.run([sys.executable, "-m", "ponte", "ir", "spec/todo.ponte", "-o", str(out)], env=env,
                       capture_output=True, text=True, timeout=20)
    assert r.returncode == 0 and json.loads(out.read_text(encoding="utf-8"))["ponte_ir"] == 1
    r = subprocess.run([sys.executable, "-m", "ponte", "conform", str(out)], env=env, capture_output=True, text=True, timeout=20)
    assert r.returncode == 0 and "4 shared tests, 4 passed" in r.stdout, r.stdout
    r = subprocess.run([sys.executable, "-m", "ponte", "guide"], env=env, capture_output=True, text=True, timeout=20)
    assert r.returncode == 0


def test_ir_doc_shows_the_real_output(tmp_path):
    import os
    import subprocess
    import sys
    env = {**os.environ, "PONTE_LANG": "en"}
    out = tmp_path / "todo.ir.json"
    subprocess.run([sys.executable, "-m", "ponte", "ir", "spec/todo.ponte", "-o", str(out)], env=env, check=True, timeout=20)
    got = subprocess.run([sys.executable, "-m", "ponte", "conform", str(out)], env=env, capture_output=True, text=True, timeout=20).stdout
    doc = open("docs/IR.md", encoding="utf-8").read()
    for line in got.strip().splitlines():
        assert line in doc, line
