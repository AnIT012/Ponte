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
