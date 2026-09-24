"""`job`: run a program of the lower layer under a contract (spec 5章 job).

    job Anticipate
      run      uv run python fails_classify.py
      at       "~/research/oops"
      with     learning_rate 1.25e-4, batch_size 32, start_from_pretrained yes, j 24
      confirm  learning_rate, batch_size, start_from_pretrained
      require  classes is 3
      require  clips_mismatch is 0
      suspect  train_accuracy above 95

`ponte job spec.ponte Anticipate` passes every `with` value as a command-line option
(`--learning_rate 1.25e-4`; `yes` becomes a bare `--start_from_pretrained`, `no` is left out;
a one-letter name becomes `-j 24`) and runs the program. The program reports facts with
`ponte.report.report(...)`; they arrive through the file named by PONTE_REPORT.

- confirm is checked while the program runs: the first mismatch stops it at once.
- require and suspect are checked on the facts reported by the end. A fact that was never
  reported fails require (unreported is not confirmed).
- Ponte knows nothing about what the program does. It only compares reported facts with the contract.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field

from .confirm import _same, names, parse_with, problems, value
from .parser import Node

CONDITION = re.compile(r"^(\w+)\s+(is|at least|at most|above|below)\s+(.+)$")


@dataclass
class Job:
    name: str
    line: int
    run: str = ""
    at: str | None = None
    settings: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)
    confirm: list[str] = field(default_factory=list)
    require: list[tuple[str, str, object, int]] = field(default_factory=list)
    suspect: list[tuple[str, str, object, int]] = field(default_factory=list)
    problems: list[tuple[int, str]] = field(default_factory=list)


def read(node: Node) -> Job:
    j = Job(node.name, node.line)
    for c in node.children:
        k, t = c.keyword, c.text.strip()
        if k == "run":
            j.run = t
        elif k == "at":
            j.at = t.strip('"')
        elif k == "with":
            j.settings, j.raw, bad = parse_with(t)
            j.problems += [(c.line, f"with は `名前 値` を , で並べます: '{b}'") for b in bad]
        elif k == "confirm":
            j.confirm = names(t)
        elif k in ("require", "suspect"):
            m = CONDITION.match(t)
            if not m:
                j.problems.append((c.line, f"{k} は `事実 is 値` / `at least` / `at most` / `above` / `below` で書きます: '{t}'"))
            else:
                (j.require if k == "require" else j.suspect).append((m.group(1), m.group(2), value(m.group(3)), c.line))
        else:
            j.problems.append((c.line, f"job に「{k}」という部品はありません（run / at / with / confirm / require / suspect）"))
    return j


def holds(fact, op: str, want) -> bool:
    v = value(fact)
    if op == "is":
        return _same(want, v)
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not isinstance(want, (int, float)):
        return False
    return {"at least": v >= want, "at most": v <= want, "above": v > want, "below": v < want}[op]


def command(j: Job) -> list[str]:
    cmd = shlex.split(j.run)
    for k, v in j.settings.items():
        flag = f"-{k}" if len(k) == 1 else f"--{k}"
        if v is True:
            cmd.append(flag)
        elif v is False:
            continue
        else:
            arg = j.raw.get(k, str(v)).strip('"')
            cmd += [flag, os.path.expanduser(arg) if arg.startswith("~") else arg]   # シェルを通さないので ~ はここで広げる
    return cmd


def judge(j: Job, facts: dict) -> list[str]:
    """Everything the facts break, after the run."""
    out = problems(j.settings, j.confirm, facts, j.raw)
    for name, op, want, line in j.require:
        if name not in facts:
            out.append(f"require {name}（L{line}）: 報告されていません")
        elif not holds(facts[name], op, want):
            out.append(f"require {name} {op} {want}（L{line}）: 実際は {facts[name]}")
    for name, op, want, line in j.suspect:
        if name in facts and holds(facts[name], op, want):
            out.append(f"suspect {name} {op} {want}（L{line}）: 実際は {facts[name]}。良すぎる／おかしい結果なので止めます。確かめてください")
    return out


def _read_facts(path: str) -> dict:
    facts = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        facts.update(json.loads(line))
                    except ValueError:
                        pass
    except FileNotFoundError:
        pass
    return facts


def run(j: Job, base_dir: str, poll: float = 0.5, out=None) -> tuple[bool, list[str], dict]:
    """Run the job. → (kept the contract, what broke it, the reported facts)"""
    out = out or sys.stdout
    fd, report = tempfile.mkstemp(prefix="ponte-report-", suffix=".jsonl")
    os.close(fd)
    cwd = os.path.expanduser(j.at) if j.at else base_dir
    env = {**os.environ, "PONTE_REPORT": report}
    try:
        proc = subprocess.Popen(command(j), cwd=cwd, env=env)
        stopped = []
        while proc.poll() is None:                     # confirm は走っている間に見る。ズレたらすぐ止める
            time.sleep(poll)
            facts = _read_facts(report)
            early = [p for p in problems(j.settings, [n for n in j.confirm if n in facts], facts, j.raw)]
            if early:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                stopped = early
                break
        facts = _read_facts(report)
        if stopped:
            return False, [f"{p}（途中で止めました）" for p in stopped], facts
        why = judge(j, facts)
        if proc.returncode:
            why.insert(0, f"プログラムが失敗しました（終了コード {proc.returncode}）")
        return not why, why, facts
    finally:
        os.unlink(report)
