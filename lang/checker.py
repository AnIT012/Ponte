"""チェッカー（仕様 v0.2 13章「エラー一覧」28個）。1つ1関数。

判定の細かい定義で仕様に書いてないものは QUESTIONS_v0.2.md に書いた（仮の扱い）。
コードが W で始まるものは警告（渡せる判定には数えない）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .icons import ICONS
from .parser import (
    Node, Spec, flow_parts, flow_states, match_arms, parse_button, relate_lines, states_of,
    thing_fields, words_entries,
)


@dataclass
class Finding:
    code: str
    line: int
    message: str

    @property
    def is_error(self) -> bool:
        return self.code.startswith("E")

    def __str__(self) -> str:
        return f"L{self.line}: {self.message}"


@dataclass
class Options:
    publish: bool = False                       # 公開する時（E26 をエラーにする）
    prev_shape: dict | None = None              # 前回のビルドの thing の形（E21）


# ---------------------------------------------------------------------------
# 共通の読み取り
# ---------------------------------------------------------------------------

BUILTIN_TYPES = {"text", "number", "count", "money", "percent", "date", "monthday",
                 "duration", "file", "image", "pdf"}


def things(spec: Spec) -> dict[str, Node]:
    return {t.name: t for t in spec.decls("thing")}


def state_table(spec: Spec) -> dict[str, dict[str, list[str]]]:
    """{thing: {項目: [状態...]}}"""
    out: dict[str, dict[str, list[str]]] = {}
    for name, t in things(spec).items():
        out[name] = {f.name: f.states for f in thing_fields(t) if f.states}
    return out


def rules(spec: Spec) -> dict[str, Node]:
    return {r.name: r for r in spec.decls("rule")}


def actions(spec: Spec) -> dict[str, Node]:
    return {a.name: a for a in spec.decls("action")}


_INLINE_MATCH = re.compile(r"(?:^|\s|=)match\s+(.+)$")


def match_nodes(spec: Spec) -> list[tuple[Node, str]]:
    """全部の match → (ノード, 何で分けるか)"""
    out = []
    for n in spec.walk():
        if n.is_decl and n.keyword == "match":
            out.append((n, n.text.split(" to ")[0].strip()))
        elif not n.is_decl:
            m = _INLINE_MATCH.search(n.raw)
            if m and "->" not in n.raw:
                out.append((n, m.group(1).strip()))
    return out


def local_states(node: Node) -> dict[str, list[str]]:
    """同じ塊（do や scene）の中で `名前[a | b]` と宣言された状態"""
    scope = node.parent
    out: dict[str, list[str]] = {}
    if scope is None:
        return out
    for c in scope.children:
        st = states_of(c.text) if c.text.startswith("[") else None
        if st:
            out[c.keyword] = st
    return out


def match_domain(spec: Spec, node: Node, subject: str) -> list[str] | None:
    """match で分ける値の取りうる状態。分からなければ None。"""
    if "." in subject:
        t, f = subject.split(".", 1)
        if t in {p.name for p in spec.decls("part")}:
            part = spec.find("part", t)
            for c in part.children:
                if c.keyword == f and c.text.startswith("["):
                    return states_of(c.text)
            return None
        return state_table(spec).get(t, {}).get(f)
    if node.is_decl:
        for sc in spec.decls("scene"):       # match tab to icon のように画面の状態で分ける
            for c in sc.children:
                if c.keyword == subject and c.text.startswith("["):
                    return states_of(c.text)
        return None
    return local_states(node).get(subject)


def match_result_states(node: Node) -> list[str] | None:
    """`kind[a | b] = match ...` の [a | b]"""
    if node.text.startswith("["):
        return states_of(node.text)
    return None


# ---------------------------------------------------------------------------
# 1. match に else が無い（全部の状態を書いた時を除く）
# ---------------------------------------------------------------------------

def check_match_else(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    for node, subject in match_nodes(spec):
        arms = match_arms(node)
        lefts = [v for ls, _, _ in arms for v in ls]
        if "else" in lefts:
            continue
        domain = match_domain(spec, node, subject)
        if domain is not None and set(domain) <= set(lefts):
            continue
        missing = f"（{', '.join(s for s in domain if s not in lefts)} が無い）" if domain else ""
        out.append(Finding("E01", node.line, f"match {subject}: else がありません{missing}"))
    return out


# ---------------------------------------------------------------------------
# 2. until に上限が無い
# ---------------------------------------------------------------------------

_LIMIT = re.compile(r"\b\d+\s+(times?|(seconds?|minutes?|hours?|days?|weeks?)\s+passed)\b")


def check_until_limit(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    for n in spec.walk():
        if re.search(r"(?<!days )\buntil\b", n.raw):   # 道具の days until は繰り返しではない
            after = n.raw.split("until", 1)[1]
            if not _LIMIT.search(after):
                out.append(Finding("E02", n.line, f"until に上限がありません（`or 3 times` か `or 1 hour passed`）: '{n.raw}'"))
    return out


# ---------------------------------------------------------------------------
# 3. action に example が2つ未満 / 4. action に else が無い
# ---------------------------------------------------------------------------

def check_examples(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    for a in actions(spec).values():
        n = len(a.children_of("example"))
        if n < 2:
            out.append(Finding("E03", a.line, f"action {a.name}: example が{n}つしかありません（最低2つ）"))
    return out


def _relate_else_targets(spec: Spec) -> dict[str, int]:
    return {a: line for a, rel, _b, line in relate_lines(spec) if rel == "else"}


def check_else(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    by_relate = _relate_else_targets(spec)
    for a in actions(spec).values():
        if a.child("else") is None and a.name not in by_relate:
            out.append(Finding("E04", a.line, f"action {a.name}: else がありません（ask user / use default ... / skip、か relate の else）"))
    return out


# ---------------------------------------------------------------------------
# 5. tbd が残っている
# ---------------------------------------------------------------------------

def check_tbd(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    for t in spec.decls("tbd"):
        items = t.children or [t]
        for it in items:
            label = it.raw if it is not t else t.text
            out.append(Finding("E05", it.line, f"tbd が残っています: 「{label}」— 決めてから渡してください"))
    return out


# ---------------------------------------------------------------------------
# 6. ## が残っている
# ---------------------------------------------------------------------------

def check_blocking(spec: Spec, opt: Options) -> list[Finding]:
    out = [Finding("E06", line, f"## が残っています（外せば承認、行ごと消せば却下）: {text}") for line, text in spec.blocking]
    for n in spec.walk():
        if n.blocking is not None:
            out.append(Finding("E06", n.line, f"## が残っています: '{n.raw}' ## {n.blocking}"))
    return out


# ---------------------------------------------------------------------------
# 7. when に状態を書いている
# ---------------------------------------------------------------------------

WHEN = [
    r"every (day|monday|tuesday|wednesday|thursday|friday|saturday|sunday) at \d{1,2}:\d{2}",
    r"at \S.*",
    r'user says ".*"',
    r"user (taps|holds) \S.*",
    r"user swipes \S+ (left|right|up|down)",
    r"user drags \S+ to \S+",
    r"user types in \S+",
    r"user (opens|leaves) \w+",
    r"user does \S.*",
    r"[A-Z][\w.]* is (created|removed)",
    r"[A-Z][\w.]* moves to \w+",
    r"[A-Z]\w* gives \S.*",
]
_WHEN = [re.compile(f"^{p}$") for p in WHEN]


def is_event(text: str) -> bool:
    return any(p.match(text.strip()) for p in _WHEN)


def check_when_is_event(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    for r in rules(spec).values():
        for w in r.children_of("when"):
            if not is_event(w.text):
                out.append(Finding("E07", w.line, f"rule {r.name}: when は出来事だけです。「{w.text}」は状態なので where に書いてください"))
    return out


# ---------------------------------------------------------------------------
# 8. move の対象が絞れていない
# ---------------------------------------------------------------------------

_MOVE = re.compile(r"^move\s+(?P<target>\S+)(?P<rest>.*?)\s+to\s+(?P<state>\w+)$")


def check_move_narrowed(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    ths = things(spec)
    for r in rules(spec).values():
        for d in r.children_of("do"):
            if not d.text.startswith("move "):
                continue
            m = _MOVE.match(d.text)
            if not m:
                out.append(Finding("E08", d.line, f"rule {r.name}: move は `move 箱 where 条件 to 状態` か `move this to 状態`: '{d.text}'"))
                continue
            if m.group("target") == "this" or m.group("target") not in ths:
                continue  # this は押された1件。画面の状態は箱ではない
            if not m.group("rest").strip().startswith("where "):
                out.append(Finding("E08", d.line, f"rule {r.name}: move の対象が絞れていません（where で絞る）: '{d.text}'"))
    return out


# ---------------------------------------------------------------------------
# 9. flow の状態にルールの抜けがある（警告）
# ---------------------------------------------------------------------------

def check_flow_coverage(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    covered: dict[str, set[str]] = {}
    for r in rules(spec).values():
        for w in r.children_of("when"):
            m = re.match(r"^(\w+) moves to (\w+)$", w.text.strip())
            if m:
                covered.setdefault(m.group(1), set()).add(m.group(2))
    for f in spec.decls("flow"):
        if "." not in f.name:
            continue
        ent = f.name.split(".")[0]
        if not covered.get(ent):
            continue
        for s in flow_states(f)[1:]:
            if s not in covered[ent]:
                out.append(Finding("W09", f.line, f"flow {f.name}: {s} のときは？（他の状態にはルールがあるのに {s} には無い）"))
    return out


# ---------------------------------------------------------------------------
# 10. 矛盾する move が同時に来うるのに > が無い
# ---------------------------------------------------------------------------

def check_conflict(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    for f in spec.decls("flow"):
        if f.name == "scene":
            continue  # 画面の移動は1人の操作なので同時には来ない
        edges, wins = flow_parts(f)
        decided = {frozenset(w) for w in wins}
        by_src: dict[str, list[str]] = {}
        for s, d in edges:
            by_src.setdefault(s, [])
            if d not in by_src[s]:
                by_src[s].append(d)
        for s, ds in by_src.items():
            for i in range(len(ds)):
                for j in range(i + 1, len(ds)):
                    if frozenset((ds[i], ds[j])) not in decided:
                        out.append(Finding("E10", f.line, f"flow {f.name}: {s} から {ds[i]} と {ds[j]} へ同時に move が来うるのに > がありません（`{ds[j]} > {ds[i]}` のように書く）"))
        states = set(flow_states(f))
        for a, b in wins:
            for x in (a, b):
                if x not in states:
                    out.append(Finding("E10", f.line, f"flow {f.name}: > の {x} は flow に無い状態です"))
    return out


# ---------------------------------------------------------------------------
# 11. list の循環参照
# ---------------------------------------------------------------------------

def check_list_cycle(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    lists = {l.name: l for l in spec.decls("list")}
    src = {n: l.child("of").text.strip() for n, l in lists.items() if l.child("of")}
    seen: set[frozenset] = set()
    for name in lists:
        path = [name]
        cur = src.get(name)
        while cur in lists:
            if cur in path:
                cyc = path[path.index(cur):] + [cur]
                if frozenset(cyc) not in seen:
                    seen.add(frozenset(cyc))
                    out.append(Finding("E11", lists[name].line, f"list の循環参照: {' -> '.join(cyc)}"))
                break
            path.append(cur)
            cur = src.get(cur)
    return out


# ---------------------------------------------------------------------------
# 12. 入れ子
# ---------------------------------------------------------------------------

LEAF = {"of", "where", "sort", "when", "why", "in", "out", "never", "else", "by", "ask",
        "given", "at", "says", "taps", "gets", "expect"}
_COMPOUND = re.compile(r"\band\b|\bor\b|[()]")


def check_nesting(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    for n in spec.walk():
        if n.keyword == "where" and not n.is_decl and _COMPOUND.search(n.text):
            out.append(Finding("E12", n.line, f"入れ子: 条件の中に条件があります。where を行で分けるか、名前付きの list に分けてください: '{n.raw}'"))
        if "->" in n.raw and re.search(r"->\s*.*\bmatch\b", n.raw):
            out.append(Finding("E12", n.line, f"入れ子: match の中に match は書けません。外に出して名前を付けてください: '{n.raw}'"))
        if n.children and not n.is_decl:
            leaf = n.keyword in LEAF or (n.keyword == "do" and n.parent is not None and n.parent.keyword == "rule")
            if leaf:
                out.append(Finding("E12", n.children[0].line, f"入れ子: `{n.keyword}` の下にさらに行は書けません: '{n.children[0].raw}'"))
        if n.is_decl and n.keyword == "group" and n.parent is not None:
            out.append(Finding("E12", n.line, "入れ子: group の中に group は書けません"))
    return out


# ---------------------------------------------------------------------------
# 13. action の契約の矛盾
# ---------------------------------------------------------------------------

_YEAR = re.compile(r"\b\d{4}\b")


def parse_out(text: str, known_types: set[str]) -> list[tuple[str | None, str | None]]:
    """`found monthday | missing` → [("found", "monthday"), ("missing", None)]
       `deadline date` → [("deadline", "date")]  /  `date` → [(None, "date")]"""
    alts = []
    for alt in [a.strip() for a in text.split("|")]:
        words = alt.split()
        if len(words) == 1:
            alts.append((None, words[0]) if words[0] in known_types else (words[0], None))
        else:
            alts.append((words[0], " ".join(words[1:])))
    return alts


def check_contract(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    known = BUILTIN_TYPES | set(things(spec))
    for a in actions(spec).values():
        o = a.child("out")
        if o is None:
            continue
        alts = parse_out(o.text, known)
        names = [n for n, _ in alts if n]
        types = [t for _, t in alts if t]
        nevers = " ".join(n.text for n in a.children_of("never"))
        if "year" in nevers and any(t.split()[0] == "date" for t in types):
            out.append(Finding("E13", o.line, f"action {a.name}: 契約の矛盾: never「{nevers}」なのに out に年の要る date があります（monthday にするか、年を決めるルールを足す）"))
        for ex in a.children_of("example"):
            if "->" not in ex.text:
                continue
            value = ex.text.split("->", 1)[1].strip()
            first = value.split()[0] if value.split() else ""
            if names and len(alts) > 1:
                if first not in names:
                    out.append(Finding("E13", ex.line, f"action {a.name}: 契約の矛盾: example の答え「{value}」が out（{o.text}）のどれにも当たりません"))
                    continue
                typ = dict(alts).get(first)
                val = value[len(first):].strip()
            else:
                typ = types[0] if types else None
                val = value
            if typ and typ.split()[0] == "date" and val and not _YEAR.search(val):
                out.append(Finding("E13", ex.line, f"action {a.name}: 契約の矛盾: out は date（年が要る）なのに example の答え「{val}」に年がありません"))
    return out


# ---------------------------------------------------------------------------
# 14. relate の then / before が一周している
# ---------------------------------------------------------------------------

def check_relate_cycle(spec: Spec, opt: Options) -> list[Finding]:
    edges: dict[str, list[tuple[str, int]]] = {}
    for a, rel, b, line in relate_lines(spec):
        if rel in ("then", "before"):
            edges.setdefault(a, []).append((b, line))
    out, seen = [], set()

    def dfs(node, path):
        for nxt, line in edges.get(node, []):
            if nxt in path:
                cyc = path[path.index(nxt):] + [nxt]
                key = frozenset(cyc)
                if key not in seen:
                    seen.add(key)
                    out.append(Finding("E14", line, f"relate が一周しています: {' -> '.join(cyc)}"))
            else:
                dfs(nxt, path + [nxt])

    for start in sorted(edges):
        dfs(start, [start])
    return out


# ---------------------------------------------------------------------------
# 15. A > B と B > A が両方ある
# ---------------------------------------------------------------------------

def check_relate_contradiction(spec: Spec, opt: Options) -> list[Finding]:
    wins = {(a, b): line for a, rel, b, line in relate_lines(spec) if rel == ">"}
    out = []
    for (a, b), line in wins.items():
        if (b, a) in wins and a < b:
            out.append(Finding("E15", line, f"relate の矛盾: {a} > {b} と {b} > {a} が両方あります"))
    return out


# ---------------------------------------------------------------------------
# 16. A before B なのに A が起きえない
# ---------------------------------------------------------------------------

def can_happen(spec: Spec) -> set[str]:
    rs, acs = rules(spec), actions(spec)
    alive = {n for n, r in rs.items() if r.child("when") is not None}
    # do の中で呼ばれる action
    for n in spec.walk():
        if n.keyword == "do":
            for name in acs:
                if re.search(rf"\b{re.escape(name)}\b", n.text):
                    alive.add(name)
    thens = [(a, b) for a, rel, b, _ in relate_lines(spec) if rel in ("then", "else")]
    changed = True
    while changed:
        changed = False
        for a, b in thens:
            if a in alive and b not in alive and (b in rs or b in acs):
                alive.add(b)
                changed = True
    return alive


def check_before_possible(spec: Spec, opt: Options) -> list[Finding]:
    alive = can_happen(spec)
    out = []
    for a, rel, b, line in relate_lines(spec):
        if rel == "before" and a not in alive:
            why = "がありません" if a not in rules(spec) and a not in actions(spec) else "は起きるきっかけ（when か then）がありません"
            out.append(Finding("E16", line, f"{a} before {b}: {a} {why}。{b} が永遠に待ちます"))
    return out


# ---------------------------------------------------------------------------
# 17. 逃げ道が2つある
# ---------------------------------------------------------------------------

def check_double_else(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    by_relate = _relate_else_targets(spec)
    for a in actions(spec).values():
        if a.child("else") is not None and a.name in by_relate:
            out.append(Finding("E17", by_relate[a.name], f"{a.name}: 逃げ道が2つあります（action の else と relate の else）。どちらか1つにしてください"))
    return out


# ---------------------------------------------------------------------------
# 18. match に宣言に無い状態がある
# ---------------------------------------------------------------------------

def check_match_states(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    for node, subject in match_nodes(spec):
        domain = match_domain(spec, node, subject)
        results = match_result_states(node)
        for lefts, right, arm in match_arms(node):
            if domain is not None:
                for v in lefts:
                    if v != "else" and v not in domain:
                        out.append(Finding("E18", arm.line, f"match {subject}: {v} は宣言に無い状態です（{' | '.join(domain)}）"))
            if results is not None:
                head = right.split()[0] if right.split() else ""
                if head not in results:
                    out.append(Finding("E18", arm.line, f"{node.keyword}: {head} は宣言した状態に無い値です（{' | '.join(results)}）"))
    return out


# ---------------------------------------------------------------------------
# 19. who が無い thing がある
# ---------------------------------------------------------------------------

_WHO = re.compile(r"^(\w+)\s+can\s+(\w+)\s+(\w+)")


def check_who(spec: Spec, opt: Options) -> list[Finding]:
    covered: set[str] = set()
    everything = False
    for w in spec.decls("who"):
        for c in w.children:
            m = _WHO.match(c.raw)
            if not m:
                continue
            if m.group(3) == "everything":
                everything = True
            covered.add(m.group(3))
    if everything:
        return []
    return [Finding("E19", t.line, f"thing {n}: 誰が何をできるか（who）が1行もありません。書いてないことは誰もできません")
            for n, t in things(spec).items() if n not in covered]


# ---------------------------------------------------------------------------
# 20. 他の箱を指す項目に gone が無い
# ---------------------------------------------------------------------------

GONE_CHOICES = {"remove too", "leave empty", "block"}


def check_gone(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    names = set(things(spec))
    for t in things(spec).values():
        for f in thing_fields(t):
            target = f.type[len("list of "):] if f.type.startswith("list of ") else f.type
            if target not in names:
                continue
            if f.gone is None:
                out.append(Finding("E20", f.line, f"{t.name}.{f.name}: {target} が消えた時どうするかがありません（gone[remove too | leave empty | block]）"))
            elif f.gone not in GONE_CHOICES:
                out.append(Finding("E20", f.line, f"{t.name}.{f.name}: gone[{f.gone}] は選べません（remove too / leave empty / block）"))
    return out


# ---------------------------------------------------------------------------
# 21. thing の形が変わったのに change が無い／足した項目の初期値が無い
# ---------------------------------------------------------------------------

def shape_of(spec: Spec) -> dict[str, dict[str, str]]:
    """thing の形。保存して次のビルドと比べる。"""
    out = {}
    for n, t in things(spec).items():
        out[n] = {f.name: (f"[{' | '.join(f.states)}]" if f.states else f.type) for f in thing_fields(t)}
    return out


def check_change(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    changes = {c.name: c for c in spec.decls("change")}
    for c in changes.values():
        for line in c.children_of("add"):
            if "=" not in line.text:
                out.append(Finding("E21", line.line, f"change {c.name}: 足した項目の初期値がありません（`add {line.text} = 値`）"))
    if opt.prev_shape is None:
        return out
    now = shape_of(spec)
    for name, fields in now.items():
        before = opt.prev_shape.get(name)
        if before is None or before == fields:
            continue
        if name not in changes:
            diff = sorted(set(before.items()) ^ set(fields.items()))
            out.append(Finding("E21", things(spec)[name].line,
                               f"thing {name}: 前のビルドから形が変わったのに change がありません（{', '.join(k for k, _ in diff)}）"))
    return out


# ---------------------------------------------------------------------------
# 22. ask ai に上限が無い
# ---------------------------------------------------------------------------

_ASK_LIMIT = re.compile(r"^limit\s+\d+(\.\d+)?\s+(seconds?|minutes?|hours?|yen|dollars?|cents?)$")


def check_ask_ai_limit(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    for a in actions(spec).values():
        ask = a.child("ask")
        if ask is None or ask.text.strip() != "ai":
            continue
        how = a.child("how")
        limits = [h for h in (how.children if how else []) if _ASK_LIMIT.match(h.raw)]
        if not limits:
            out.append(Finding("E22", ask.line, f"action {a.name}: ask ai は実行の度にAIを呼ぶので、how に時間かお金の上限が要ります（limit 5 seconds / limit 1 yen）"))
    return out


# ---------------------------------------------------------------------------
# 23. connect の does の失敗の逃げ道が無い
# ---------------------------------------------------------------------------

def check_connect_fallback(spec: Spec, opt: Options) -> list[Finding]:
    verbs: dict[str, list[str]] = {}
    for c in spec.decls("connect"):
        for d in c.children_of("does"):
            verbs.setdefault(c.name, []).append(d.text.split("->")[0].split(",")[0].split()[0:2])
    out = []
    by_relate = _relate_else_targets(spec)
    for r in rules(spec).values():
        for d in r.children_of("do"):
            words = d.text.split()
            if len(words) < 2 or words[0] not in verbs:
                continue
            for v in verbs[words[0]]:
                if words[1:1 + len(v)] == v and r.name not in by_relate:
                    out.append(Finding("E23", d.line, f"rule {r.name}: {words[0]} の {' '.join(v)} が失敗した時の逃げ道がありません（relate に `{r.name} else 〇〇`）"))
    return out


# ---------------------------------------------------------------------------
# 24. flow scene に無い画面の移動
# ---------------------------------------------------------------------------

def check_scene_move(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    scenes = {s.name: s for s in spec.decls("scene")}
    scenes.update({i.name: i for i in spec.decls("input")})  # input も1つの画面
    fs = next((f for f in spec.decls("flow") if f.name == "scene"), None)
    edges = set(flow_parts(fs)[0]) if fs else set()
    for r in rules(spec).values():
        for d in r.children_of("do"):
            m = re.match(r"^go\s+(\w+)", d.text)
            if not m:
                continue
            dst = m.group(1)
            if dst not in scenes:
                out.append(Finding("E24", d.line, f"rule {r.name}: {dst} という scene はありません"))
                continue
            if fs is None:
                out.append(Finding("E24", d.line, f"rule {r.name}: 画面の移動があるのに flow scene がありません"))
                continue
            # どの scene からの移動か: when から推測する
            srcs = set()
            w = r.child("when")
            if w is not None:
                mo = re.match(r"^user (?:opens|leaves) (\w+)$", w.text)
                if mo:
                    srcs.add(mo.group(1))
                mt = re.search(r"\bon (\w+)$", w.text)
                if mt:
                    for sn, s in scenes.items():
                        if any(re.search(rf"\b{mt.group(1)}\b", n.raw) for n in s.walk() if n is not s):
                            srcs.add(sn)
            if srcs:
                if not any((s, dst) in edges for s in srcs):
                    out.append(Finding("E24", d.line, f"rule {r.name}: {' / '.join(sorted(srcs))} から {dst} への移動が flow scene にありません"))
            elif not any(d2 == dst for _, d2 in edges):
                out.append(Finding("E24", d.line, f"rule {r.name}: {dst} への移動が flow scene にありません"))
    return out


# ---------------------------------------------------------------------------
# 25. words に片方の言語の訳が無い
# ---------------------------------------------------------------------------

def check_words(spec: Spec, opt: Options) -> list[Finding]:
    blocks = spec.decls("words")
    keys = {w.name: set(words_entries(w)) for w in blocks}
    every = set().union(*keys.values()) if keys else set()
    out = []
    for w in blocks:
        for k in sorted(every - keys[w.name]):
            out.append(Finding("E25", w.line, f"words {w.name}: 「{k}」の訳がありません"))
    return out


# ---------------------------------------------------------------------------
# 26. 名前の無いボタン・説明の無い画像（公開する時だけエラー）
# ---------------------------------------------------------------------------

def check_a11y(spec: Spec, opt: Options) -> list[Finding]:
    code = "E26" if opt.publish else "W26"
    out = []
    ui = [d for d in spec.decls() if d.keyword in ("scene", "look", "part")]
    for n in (x for d in ui for x in d.walk() if x is not d):
        if re.search(r"(?<![\w-])button\s+\S+", n.raw) and " named " not in f" {n.raw} ":
            out.append(Finding(code, n.line, f"ボタンに名前がありません（読み上げで何のボタンか分からない）。`named 〇〇` を足してください: '{n.raw}'"))
        if re.search(r"(?<![\w-])image\s+\S+", n.raw) and " about " not in f" {n.raw} ":
            out.append(Finding(code, n.line, f"画像に説明がありません。`about 〇〇` を足してください: '{n.raw}'"))
    return out


# ---------------------------------------------------------------------------
# 27. 通貨の違う money を足している
# ---------------------------------------------------------------------------

def check_money(spec: Spec, opt: Options) -> list[Finding]:
    cur: dict[str, str] = {}
    for t in things(spec).values():
        for f in thing_fields(t):
            m = re.match(r"^money\s+(\w+)", f.type)
            if m:
                cur[f.name] = m.group(1)
    if len(set(cur.values())) < 2:
        return []
    out = []
    for n in spec.walk():
        if n.is_decl or not re.search(r"[+\-]|\bsum\b", n.raw):
            continue
        used = {cur[w] for w in re.findall(r"\w+", n.raw) if w in cur}
        if len(used) > 1:
            out.append(Finding("E27", n.line, f"通貨の違うお金を足しています（{', '.join(sorted(used))}）: '{n.raw}'"))
    return out


# ---------------------------------------------------------------------------
# 28. 定義されていない名前（v0.2 の相談で追加）
# ---------------------------------------------------------------------------

def check_undefined(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    ths, lists = set(things(spec)), {l.name for l in spec.decls("list")}
    parts = {p.name for p in spec.decls("part")}
    scenes = {x.name for x in spec.decls("scene")} | {i.name for i in spec.decls("input")}
    looks = {l.name for l in spec.decls("look")}
    callables = set(rules(spec)) | set(actions(spec))

    def need(name, kinds, line, where):
        if name not in kinds:
            out.append(Finding("E28", line, f"{where}: 「{name}」がどこにも定義されていません"))

    def slot(text, line, where):
        text = text.strip()
        if not text or text == "nothing" or text.startswith(("button ", "match ")):
            return
        if text.startswith("tabs "):
            return
        m = re.match(r"^(\w+) as \w+$", text)
        if m:
            if m.group(1) != "this":
                need(m.group(1), ths | lists | parts, line, where)
        elif re.fullmatch(r"[A-Z]\w*", text):
            need(text, parts | looks, line, where)

    for sc in spec.decls("scene"):
        for c in sc.walk():
            if c is sc or c.text.startswith("["):
                continue
            if "->" in c.raw:
                slot(c.raw.split("->", 1)[1], c.line, f"scene {sc.name}")
            elif c.parent is sc:
                slot(c.text, c.line, f"scene {sc.name}")
    for lk in spec.decls("look"):
        need(lk.name, ths | lists, lk.line, "look")
        for c in lk.children:
            m = re.match(r"^([A-Z]\w*) of \w+$", c.text)
            if m:
                need(m.group(1), parts, c.line, f"look {lk.name}")
    for f in spec.decls("flow"):
        if f.name == "scene":
            for a, b in flow_parts(f)[0]:
                need(a, scenes, f.line, "flow scene")
                need(b, scenes, f.line, "flow scene")
    for l in spec.decls("list"):
        of = l.child("of")
        if of is not None:
            need(of.text.strip(), ths | lists, of.line, f"list {l.name}")
    for a, rel, b, line in relate_lines(spec):
        if rel != "before":          # before の左は E16 が見る
            need(a, callables, line, "relate")
        need(b, callables, line, "relate")
    # ボタンの行・アイコン
    for d in spec.decls():
        if d.keyword not in ("scene", "look"):
            continue
        for c in d.walk():
            m = re.search(r"(?:^|\s)button\s+(.+)$", c.raw) if c is not d else None
            if not m:
                continue
            b = parse_button(m.group(1))
            if b is None:
                out.append(Finding("E28", c.line, f"ボタンの書き方が分かりません（button 名前 named 文字 [icon 名前] [confirm \"文\"] [toggle 状態 / set 状態 値]）: '{c.raw}'"))
            elif b["icon"] and b["icon"] not in ICONS:
                out.append(Finding("E28", c.line, f"アイコン「{b['icon']}」はありません（使えるのは {', '.join(sorted(ICONS))}）"))
    for m in spec.decls("match"):
        if m.text.endswith(" to icon"):
            for _, right, arm in match_arms(m):
                if right not in ICONS:
                    out.append(Finding("E28", arm.line, f"アイコン「{right}」はありません"))
    # look の項目名
    fields_of = {n: {f.name for f in thing_fields(t)} for n, t in things(spec).items()}
    def thing_of(name):
        seen = set()
        while name in lists and name not in seen:
            seen.add(name)
            name = spec.find("list", name).child("of").text.strip()
        return name
    for lk in spec.decls("look"):
        flds = fields_of.get(thing_of(lk.name), set())
        for c in lk.children:
            names = []
            if c.keyword in ("title", "lead"):
                names = [c.text.strip()]
            elif c.keyword == "search":
                names = [x.strip() for x in c.text.split(",")]
            elif c.keyword == "group" and c.text.startswith("by "):
                names = [c.text[3:].strip()]
            elif c.keyword == "sub" and re.fullmatch(r"\w+", c.text.strip()):
                names = [c.text.strip()]
            for n in names:
                if flds and n not in flds:
                    out.append(Finding("E28", c.line, f"look {lk.name}: 「{n}」という項目はありません（{', '.join(sorted(flds))}）"))
    return out


# ---------------------------------------------------------------------------

ALL_CHECKS = [
    check_match_else, check_until_limit, check_examples, check_else, check_tbd,
    check_blocking, check_when_is_event, check_move_narrowed, check_flow_coverage,
    check_conflict, check_list_cycle, check_nesting, check_contract,
    check_relate_cycle, check_relate_contradiction, check_before_possible,
    check_double_else, check_match_states, check_who, check_gone, check_change,
    check_ask_ai_limit, check_connect_fallback, check_scene_move, check_words,
    check_a11y, check_money, check_undefined,
]


def check(spec: Spec, opt: Options | None = None) -> list[Finding]:
    opt = opt or Options()
    found: list[Finding] = []
    for fn in ALL_CHECKS:
        found.extend(fn(spec, opt))
    found.sort(key=lambda f: (f.line, f.code))
    return found
