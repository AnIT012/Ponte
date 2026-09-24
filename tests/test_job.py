"""job（仕様 5章 job）: 下の層のプログラムを約束付きで走らせる。研究で実際にあった「黙って壊れる」を止める。"""
import os
import sys
import time

import pytest

from ponte.checker import check
from ponte.job import command, read, run
from ponte.parser import parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TRAIN = '''
import argparse, sys, time
sys.path.insert(0, ROOT)
from ponte.report import report, lr_of, batch_of
p = argparse.ArgumentParser()
p.add_argument("--learning_rate", type=float, default=1e-3)
p.add_argument("--batch_size", type=int, default=8)
p.add_argument("--start_from_pretrained", action="store_true")
p.add_argument("-j", type=int, default=1)
a = p.parse_args()
class Adam:
    def __init__(self, params, lr=1e-3, eps=1e-8): self.param_groups = [{"lr": lr}]
class Loader:
    def __init__(self, batch_size): self.batch_size = batch_size
optimizer = OPTIMIZER
loader = Loader(a.batch_size)
report(learning_rate=lr_of(optimizer), batch_size=batch_of(loader), start_from_pretrained=PRETRAINED)
time.sleep(SLEEP)                                    # ここで何日も学習する
report(classes=CLASSES, clips_mismatch=MISMATCH, train_accuracy=ACC)
sys.exit(EXIT)
'''

GOOD = dict(OPTIMIZER="Adam([], lr=a.learning_rate, eps=1e-4)", PRETRAINED="a.start_from_pretrained",
            SLEEP="0", CLASSES="3", MISMATCH="0", ACC="67.3", EXIT="0")

SPEC = """job Anticipate
  run      {py} train.py
  with     learning_rate 1.25e-4, batch_size 32, start_from_pretrained yes, j 24
  confirm  learning_rate, batch_size, start_from_pretrained
  require  classes is 3
  require  clips_mismatch is 0
  suspect  train_accuracy above 95
"""


def go(tmp_path, **over):
    vals = {**GOOD, **over}
    src = TRAIN.replace("ROOT", repr(ROOT))
    for k, v in vals.items():
        src = src.replace(k, v)
    (tmp_path / "train.py").write_text(src, encoding="utf-8")
    spec = parse(SPEC.format(py=sys.executable))
    assert [f for f in check(spec) if f.is_error] == []
    return run(read(spec.find("job", "Anticipate")), str(tmp_path), poll=0.05)


def test_command_line_is_built_from_with():
    j = read(parse(SPEC.format(py="python")).find("job", "Anticipate"))
    assert command(j) == ["python", "train.py", "--learning_rate", "1.25e-4", "--batch_size", "32",
                          "--start_from_pretrained", "-j", "24"]


def test_a_run_that_keeps_the_contract_passes(tmp_path):
    ok, why, facts = go(tmp_path)
    assert ok, why
    assert facts["train_accuracy"] == 67.3


def test_dropped_learning_rate_stops_the_run_early(tmp_path):
    """⑥: Adam に lr= が無く、既定の 1e-3 のまま。学習を待たずにその場で止める"""
    t = time.time()
    ok, why, _ = go(tmp_path, OPTIMIZER="Adam([], eps=1e-4)", SLEEP="30")
    assert not ok and "confirm learning_rate" in why[0] and "途中で止めました" in why[0]
    assert time.time() - t < 15


@pytest.mark.parametrize("over,needle", [
    (dict(PRETRAINED="False"), "confirm start_from_pretrained"),        # ⑤ 事前学習が読まれていない
    (dict(CLASSES="1"), "require classes"),                              # ① 1クラスしかない
    (dict(MISMATCH="5"), "require clips_mismatch"),                      # ③⑧ clips と labels のズレ
    (dict(ACC="99.9"), "suspect train_accuracy"),                        # ① 良すぎる数字
    (dict(EXIT="1"), "終了コード 1"),
])
def test_silent_breakage_is_stopped(tmp_path, over, needle):
    ok, why, _ = go(tmp_path, **over)
    assert not ok and any(needle in w for w in why), why


def test_a_fact_never_reported_fails_require(tmp_path):
    ok, why, _ = go(tmp_path, MISMATCH="0) if False else report(x=0")   # clips_mismatch を報告しない
    assert not ok and any("require clips_mismatch" in w and "報告されていません" in w for w in why), why


def codes(src):
    return [f.code for f in check(parse(src)) if f.is_error]


def test_job_contract_is_checked():
    assert "E28" in codes("job J\n  with  lr 1\n")                                    # run がない
    assert "E32" in codes("job J\n  run  python t.py\n  with  lr 1\n  confirm  lrr\n")
    assert "E31" in codes("job J\n  run  python t.py\n  require  accuracy high\n")
