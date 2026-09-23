"""チェッカー。仕様6章「エラー一覧（決めてないことはエラー）」の12個。1つ1関数。

  1. match に otherwise が無い ........................ check_match_otherwise
  2. until に上限が無い .............................. check_until_limit
  3. action / derive に example が2つ未満 ............. check_examples
  4. action / derive に else が無い ................... check_else
  5. unknown が残っている ............................ check_unknown
  6. proposed が承認されていない ..................... check_proposed
  7. when に状態を書いている ......................... check_when_is_event
  8. move の対象が絞れていない ....................... check_move_narrowed
  9. flow の状態にルールの抜けがある（警告） ......... check_flow_coverage
 10. 矛盾する move が同時に来うるのに on conflict が無い check_on_conflict
 11. list の循環参照 ................................ check_list_cycle
 12. 入れ子 ........................................ check_nesting

判定の細かい定義は QUESTIONS.md の B 節を参照（仕様に無い部分は仮）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .parser import (
    Node, Spec, flow_conflicts, flow_states, flow_target, flow_transitions,
)


@dataclass
class Finding:
    code: str        # 例 "E01"。W で始まるものは警告
    line: int
    message: str

    @property
    def is_error(self) -> bool:
        return self.code.startswith("E")

    def __str__(self) -> str:
        return f"L{self.line}: {self.message}"


# ---------------------------------------------------------------------------
# 1. match に otherwise が無い
# ---------------------------------------------------------------------------

def check_match_otherwise(spec: Spec) -> list[Finding]:
    out = []
    for m in spec.decls_of("match"):
        if m.child("otherwise") is None:
            out.append(Finding("E01", m.line, f"match {m.name}: otherwise がありません（表の抜け漏れ）"))
    return out


# ---------------------------------------------------------------------------
# 2. until に上限が無い
# ---------------------------------------------------------------------------

_LIMIT_COUNT = re.compile(r"\b\d+\s+times?\b")
_LIMIT_TIME = re.compile(r"\b\d+\s+(seconds?|minutes?|hours?|days?|weeks?)\s+passed\b")


def _has_limit(until_text: str) -> bool:
    return bool(_LIMIT_COUNT.search(until_text) or _LIMIT_TIME.search(until_text))


def check_until_limit(spec: Spec) -> list[Finding]:
    out = []
    for n in spec.walk():
        if " until " in f" {n.raw} " or n.keyword == "until":
            after = n.raw.split("until", 1)[1]
            if not _has_limit(after):
                out.append(Finding(
                    "E02", n.line,
                    f"until に上限がありません（`N times` か `N hours passed` を or で足す）: '{n.raw}'",
                ))
    return out


# ---------------------------------------------------------------------------
# 3. / 4. action / derive の example と else
# ---------------------------------------------------------------------------

def _contracts(spec: Spec) -> list[Node]:
    """action と derive（どこにあっても）"""
    return [n for n in spec.walk() if n.keyword in ("action", "derive")]


def check_examples(spec: Spec) -> list[Finding]:
    out = []
    for a in _contracts(spec):
        count = len(a.children_of("example"))
        if count < 2:
            out.append(Finding("E03", a.line, f"{a.keyword} {a.name}: example が{count}つしかありません（最低2つ）"))
    return out


def check_else(spec: Spec) -> list[Finding]:
    out = []
    for a in _contracts(spec):
        if a.child("else") is None:
            out.append(Finding("E04", a.line, f"{a.keyword} {a.name}: else がありません（自信がないときの逃げ道: ask user / use default ... / skip）"))
    return out


# ---------------------------------------------------------------------------
# 5. unknown が残っている
# ---------------------------------------------------------------------------

def check_unknown(spec: Spec) -> list[Finding]:
    out = []
    for u in spec.decls_of("unknown"):
        items = u.children or [u]
        for item in items:
            label = item.raw if item is not u else u.text
            out.append(Finding("E05", item.line, f"unknown が残っています: 「{label}」— 決めてから渡してください"))
    return out


# ---------------------------------------------------------------------------
# 6. proposed が承認されていない
# ---------------------------------------------------------------------------

def check_proposed(spec: Spec) -> list[Finding]:
    out = []
    for n in spec.walk():
        if n.proposed:
            out.append(Finding("E06", n.line, f"AIの提案が承認されていません（マーカーを外せば承認）: '{n.raw}  # {n.comment}'"))
    return out


# ---------------------------------------------------------------------------
# 7. when に状態を書いている（when は出来事だけ。閉じたリスト）
# ---------------------------------------------------------------------------

WHEN_PATTERNS = [
    ("time",     re.compile(r"^every (day|monday|tuesday|wednesday|thursday|friday|saturday|sunday) at \d{1,2}:\d{2}$")),
    ("time",     re.compile(r"^at \S.*$")),
    ("user",     re.compile(r'^user says ".*"$')),
    ("user",     re.compile(r"^user does \S.*$")),
    ("data",     re.compile(r"^[A-Z]\w* is created$")),
    ("data",     re.compile(r"^[A-Z]\w* is removed$")),
    ("data",     re.compile(r"^[A-Z]\w* moves to \w+$")),
    ("external", re.compile(r"^\w+ sends \S.*$")),
]


def classify_when(text: str) -> str | None:
    for kind, pat in WHEN_PATTERNS:
        if pat.match(text.strip()):
            return kind
    return None


def check_when_is_event(spec: Spec) -> list[Finding]:
    out = []
    for r in spec.decls_of("rule"):
        for w in r.children_of("when"):
            if classify_when(w.text) is None:
                out.append(Finding(
                    "E07", w.line,
                    f"rule {r.name}: when は出来事だけです。「{w.text}」は状態なので where に書いてください"
                    "（書ける出来事: every day at 21:00 / at 9/24 23:00 / user says \"...\" / user does 〇〇 / "
                    "〇〇 is created / 〇〇 moves to 状態 / 〇〇 is removed / 〇〇 sends 〇〇）",
                ))
    return out


# ---------------------------------------------------------------------------
# 8. move の対象が絞れていない
# ---------------------------------------------------------------------------

_MOVE = re.compile(r"^move\s+(?P<target>\w+)(?P<rest>.*?)\s+to\s+(?P<state>\w+)$")


def parse_move(do_text: str) -> dict | None:
    """`move Application where company is {company} to submitted`
    → {"target": "Application", "where": "company is {company}", "state": "submitted"}"""
    m = _MOVE.match(do_text.strip())
    if not m:
        return None
    rest = m.group("rest").strip()
    where = rest[len("where"):].strip() if rest.startswith("where") else ""
    return {"target": m.group("target"), "where": where, "state": m.group("state")}


def check_move_narrowed(spec: Spec) -> list[Finding]:
    out = []
    for r in spec.decls_of("rule"):
        for d in r.children_of("do"):
            if not d.text.startswith("move"):
                continue
            mv = parse_move(d.text)
            if mv is None:
                out.append(Finding("E08", d.line, f"rule {r.name}: move は `move 箱 where 条件 to 状態` で書きます: '{d.text}'"))
            elif not mv["where"]:
                out.append(Finding("E08", d.line, f"rule {r.name}: move の対象が絞れていません（where で絞る）: '{d.text}'"))
    return out


# ---------------------------------------------------------------------------
# 9. flow の状態にルールの抜けがある（警告）
# ---------------------------------------------------------------------------

def check_flow_coverage(spec: Spec) -> list[Finding]:
    out = []
    moves_to: dict[str, set[str]] = {}
    for r in spec.decls_of("rule"):
        for w in r.children_of("when"):
            m = re.match(r"^(\w+) moves to (\w+)$", w.text.strip())
            if m:
                moves_to.setdefault(m.group(1), set()).add(m.group(2))
    for f in spec.decls_of("flow"):
        entity, _ = flow_target(f)
        covered = moves_to.get(entity)
        if not covered:
            continue  # 状態ごとのルールを書いていないなら、抜けとは言わない
        states = flow_states(f)
        missing = [s for s in states[1:] if s not in covered]
        for s in missing:
            out.append(Finding("W09", f.line, f"flow {f.name}: {s} のときは？（他の状態にはルールがあるのに {s} には無い）"))
    return out


# ---------------------------------------------------------------------------
# 10. 矛盾する move が同時に来うるのに on conflict が無い
# ---------------------------------------------------------------------------

def check_on_conflict(spec: Spec) -> list[Finding]:
    out = []
    for f in spec.decls_of("flow"):
        conflicts = flow_conflicts(f)
        decided = {frozenset(p) for p in conflicts}
        by_src: dict[str, list[str]] = {}
        for s, d in flow_transitions(f):
            by_src.setdefault(s, [])
            if d not in by_src[s]:
                by_src[s].append(d)
        for s, dsts in by_src.items():
            for i in range(len(dsts)):
                for j in range(i + 1, len(dsts)):
                    a, b = dsts[i], dsts[j]
                    if frozenset((a, b)) not in decided:
                        out.append(Finding(
                            "E10", f.line,
                            f"flow {f.name}: {s} から {a} と {b} へ同時に move が来うるのに on conflict がありません"
                            f"（`on conflict {a} wins over {b}` のように書く）",
                        ))
        # on conflict に flow に無い状態が書かれている
        states = set(flow_states(f))
        for w, l in conflicts:
            for x in (w, l):
                if x not in states:
                    out.append(Finding("E10", f.line, f"flow {f.name}: on conflict の {x} は flow に無い状態です"))
    return out


# ---------------------------------------------------------------------------
# 11. list の循環参照
# ---------------------------------------------------------------------------

def check_list_cycle(spec: Spec) -> list[Finding]:
    out = []
    lists = {l.name: l for l in spec.decls_of("list")}
    src: dict[str, str] = {}
    for name, l in lists.items():
        fr = l.child("from")
        if fr is not None:
            src[name] = fr.text.strip()
    reported: set[str] = set()
    for name in lists:
        path = [name]
        cur = src.get(name)
        while cur in lists:
            if cur in path:
                cycle = path[path.index(cur):] + [cur]
                key = frozenset(cycle)
                if key not in reported:
                    reported.add(key)
                    out.append(Finding("E11", lists[name].line, f"list の循環参照: {' -> '.join(cycle)}"))
                break
            path.append(cur)
            cur = src.get(cur)
    return out


# ---------------------------------------------------------------------------
# 12. 入れ子
# ---------------------------------------------------------------------------

# 子を持てる節。それ以外の節の下に行があれば入れ子
CAN_HAVE_CHILDREN = {"how", "example", "derive", "unknown"}
LEAF_CLAUSES = {"from", "where", "sort by", "when", "do", "because", "input", "output",
                "never", "else", "by", "use", "otherwise", "on conflict"}
_COMPOUND = re.compile(r"\band\b|\bor\b|[()]")


def check_nesting(spec: Spec) -> list[Finding]:
    out = []
    for n in spec.walk():
        if n.indent == 0:
            continue
        if n.keyword == "where" and _COMPOUND.search(n.text):
            out.append(Finding("E12", n.line, f"入れ子: 条件の中に条件があります。名前付きの list に分けてください: '{n.raw}'"))
        if n.keyword == "do" and n.child("where") is not None:
            out.append(Finding("E12", n.child("where").line, "入れ子: do の下に where は書けません。list で先に絞ってから do に使ってください"))
        elif n.children and n.keyword in LEAF_CLAUSES:
            out.append(Finding("E12", n.children[0].line, f"入れ子: `{n.keyword}` の下にさらに行は書けません: '{n.children[0].raw}'"))
    return out


# ---------------------------------------------------------------------------
# 全部まとめて
# ---------------------------------------------------------------------------

ALL_CHECKS = [
    check_match_otherwise,
    check_until_limit,
    check_examples,
    check_else,
    check_unknown,
    check_proposed,
    check_when_is_event,
    check_move_narrowed,
    check_flow_coverage,
    check_on_conflict,
    check_list_cycle,
    check_nesting,
]


def check(spec: Spec) -> list[Finding]:
    findings: list[Finding] = []
    for fn in ALL_CHECKS:
        findings.extend(fn(spec))
    findings.sort(key=lambda f: (f.line, f.code))
    return findings
