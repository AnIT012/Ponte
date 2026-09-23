"""チェッカー（仕様 v0.3 13章「エラー一覧」32個）。1つ1関数。

判定の細かい定義で仕様に書いてないものは QUESTIONS_v0.2.md に書いた（仮の扱い）。
コードが W で始まるものは警告（渡せる判定には数えない）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .forms import DO_FORMS as _DO_DOC, VALUE_FORMS, WHEN_FORMS
from .icons import ICONS
from .parser import (
    Node, ParseError, Spec, flow_parts, flow_states, match_arms, parse_button, relate_lines, states_of,
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
            for c in part.walk():
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
    """`kind[a | b] = match ...` の [a | b]。`[found monthday | missing]` は状態の名前 found / missing として読む"""
    if node.text.startswith("["):
        states = states_of(node.text) or []          # `[` だけで閉じていない時は、形の検査が別に止める
        return [x.split()[0] for x in states if x.split()] or None
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

WHEN = [f[0] for f in WHEN_FORMS if f[4]]
WHEN_LATER = [(re.compile(f"^{f[0]}$"), f[1]) for f in WHEN_FORMS if not f[4]]
_WHEN = [re.compile(f"^{p}$") for p in WHEN]


def is_event(text: str) -> bool:
    return any(p.match(text.strip()) for p in _WHEN)


def check_when_is_event(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    for r in rules(spec).values():
        for w in r.children_of("when"):
            later = next((form for p, form in WHEN_LATER if p.match(w.text.strip())), None)
            if later:
                out.append(Finding("E07", w.line, f"rule {r.name}: `{later}` はまだ実行エンジンが起こしません（書いても動かないので止めます）"))
            elif not is_event(w.text):
                t = w.text.strip()
                if re.match(r"^(every|at|user)\b|^[A-Z]\w*\s+(is|moves|gives)\b", t):   # 出来事のつもりで、書き方が違う
                    import difflib
                    forms = [f[1] for f in WHEN_FORMS if f[4]]
                    near = difflib.get_close_matches(t, forms + [f[3] for f in WHEN_FORMS if f[4]], n=1, cutoff=0.3)
                    hint = f"。近い書き方: `{near[0]}`" if near else f"（書ける形: {' / '.join(forms)}）"
                    out.append(Finding("E07", w.line, f"rule {r.name}: when の書き方が分かりません: 「{t}」{hint}"))
                else:
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
        "at", "says", "gets"}
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
            if leaf and n.keyword == "do" and n.text.startswith("create "):   # create の下は「項目 値」
                for c in n.children:
                    if c.children:
                        out.append(Finding("E12", c.children[0].line, "入れ子: create の中身の下に、さらに行は書けません"))
            elif leaf:
                out.append(Finding("E12", n.children[0].line, f"入れ子: `{n.keyword}` の下にさらに行は書けません: '{n.children[0].raw}'"))
        if n.keyword in ("given", "taps", "expect", "adds") and not n.is_decl:
            if re.search(r"\w\(", n.text):
                out.append(Finding("E12", n.line, f"example の箱の中身は、カッコではなく字下げして1行1つで書きます（`{n.keyword} {n.text.split('(')[0].strip()}` の下に `項目 値`）"))
            for c in n.children:
                if c.children:
                    out.append(Finding("E12", c.children[0].line, "入れ子: example の箱の中身の下に、さらに行は書けません"))
        if n.is_decl and n.keyword == "part":
            for c in n.children:
                if re.match(r"^\w+\s*(\[[^\]]*\])?\s*=", c.raw):
                    out.append(Finding("E12", c.line, f"part {n.name}: 部品の中の計算は do の下に書きます（action の中身と同じ）: '{c.raw}'"))
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
        if not words:                 # `found |` のような空の選択肢は、呼ぶ側が形の違いとして見つける
            continue
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

def ui_texts(spec: Spec) -> list[tuple[str, int]]:
    """画面に出る文字（ボタンの名前・見出し・空の時の文・確認の文・部品の文と、部品が計算する文）"""
    out = []
    for d in spec.decls():
        if d.keyword not in ("scene", "look", "part"):
            continue
        for c in d.walk():
            if c is d:
                continue
            m = re.search(r"(?:^|\s)button\s+(.+)$", c.raw)
            if m and (b := parse_button(m.group(1))):
                if b["label"]:
                    out.append((b["label"], c.line))
                if b["confirm"]:
                    out.append((b["confirm"], c.line))
            if c.keyword in ("heading", "empty") and c.parent is d:
                t = re.findall(r'"[^"]*"|\S+', c.text)
                if t:
                    out.append((t[0].strip('"'), c.line))
            st = re.search(r"(?:^|\s)stats\s+(.+)$", c.raw)
            if st:                                 # stats の見出し（一覧の名前・合計する項目）
                for x in st.group(1).split(","):
                    out += [(w, c.line) for w in re.findall(r"\w+", x) if w not in ("sum", "of")]
            if c.keyword == "show" and c.text.startswith("text "):
                out.append((c.text[5:].strip().strip('"'), c.line))
            if d.keyword == "part" and "->" in c.raw:
                right = c.raw.split("->", 1)[1].strip()
                if right.startswith('"'):
                    out.append((right.strip('"'), c.line))
    return out


def check_words(spec: Spec, opt: Options) -> list[Finding]:
    blocks = spec.decls("words")
    keys = {w.name: set(words_entries(w)) for w in blocks}
    every = set().union(*keys.values()) if keys else set()
    out = []
    for w in blocks:
        for k in sorted(every - keys[w.name]):
            out.append(Finding("E25", w.line, f"words {w.name}: 「{k}」の訳がありません"))
    if blocks:   # words がある spec では、画面の文字は words の名前で書く（日本語を2回書かない）
        for text, line in ui_texts(spec):
            missing = [w for w, ks in keys.items() if text not in ks]
            if missing:
                out.append(Finding("E25", line, f"画面の文字「{text}」が words に無い（{', '.join(missing)}）。words の名前で書いて、words に訳を書く"))
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
# （list の sort の項目名と向きもここで見る）
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
            out.append(Finding("E28", line, f"{where}: 「{name}」がどこにも定義されていません{did_you_mean(name, kinds, '（もしかして {}？）')}"))

    def slot(text, line, where):
        text = text.strip()
        if not text or text == "nothing" or text.startswith(("button ", "match ")):
            return
        if text.startswith("tabs "):
            return
        if text.startswith("stats "):
            for x in text[6:].split(","):
                m = re.fullmatch(r"(?:sum \w+ of )?(\w+)", x.strip())
                if not m:
                    out.append(Finding("E28", line, f"{where}: stats の書き方が分かりません: '{x.strip()}'（一覧の名前 / sum 項目 of 一覧）"))
                else:
                    need(m.group(1), lists, line, where)
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
        else:
            out.append(Finding("E28", l.line, f"list {l.name}: 何の一覧かがありません（`of Task` のように書く）"))
        so = l.child("sort")
        if so is not None:
            w = so.text.split()
            if len(w) > 2 or (len(w) == 2 and w[1] not in ("asc", "desc")):
                out.append(Finding("E28", so.line, f"list {l.name}: sort は `sort 項目` か `sort 項目 desc` です: '{so.raw}'"))
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
    for st in spec.decls("style"):
        for c in st.children:
            if re.search(r"\btone\b", c.text):
                out.append(Finding("E28", c.line, f"style {st.name}: tone はボタンの行に書きます（`button {c.keyword} named ... tone {c.text.split()[-1]}`）"))
    for m in spec.decls("match"):
        if m.text.endswith(" to icon"):
            for _, right, arm in match_arms(m):
                if right not in ICONS:
                    out.append(Finding("E28", arm.line, f"アイコン「{right}」はありません"))
    # 項目の型（組み込みの型・thing・connect が持ってくる型のどれか）
    conn_types = set()
    for c in spec.decls("connect"):
        for g in c.children:
            if g.keyword in ("gives", "does"):
                conn_types |= set(re.findall(r"\b[A-Z]\w*\b", g.text))
    known_types = BUILTIN_TYPES | ths | conn_types
    for t in things(spec).values():
        for f in thing_fields(t):
            if f.states:
                continue
            base = f.type[len("list of "):] if f.type.startswith("list of ") else f.type
            base = base.split()[0]
            if base not in known_types:
                out.append(Finding("E28", f.line, f"{t.name}.{f.name}: 型「{base}」がどこにも定義されていません（{', '.join(sorted(BUILTIN_TYPES))} か thing の名前）{did_you_mean(base, set(BUILTIN_TYPES) | set(known_types))}"))
    for a in actions(spec).values():
        i = a.child("in")
        if i is not None and len(i.text.split()) >= 2:
            base = i.text.split()[1]
            if base not in known_types:
                out.append(Finding("E28", i.line, f"action {a.name}: in の型「{base}」がどこにも定義されていません"))
    # look の項目名
    fields_of = {n: {f.name for f in thing_fields(t)} for n, t in things(spec).items()}
    def thing_of(name):
        seen = set()
        while name in lists and name not in seen:
            seen.add(name)
            of = spec.find("list", name).child("of")
            if of is None:
                break
            name = of.text.strip()
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
            elif c.keyword == "image":                # 画像を見せる（image の項目だけ）
                names = [c.text.strip().split(" about ")[0].strip()]
                t = things(spec).get(thing_of(lk.name))
                ty = next((f.type for f in thing_fields(t) if f.name == names[0]), None) if t is not None else None
                if ty is not None and ty != "image":
                    out.append(Finding("E32", c.line, f"look {lk.name}: image は画像の項目だけです（{names[0]} は {ty}）"))
            elif c.keyword == "sum":                  # as chart の高さ（数の項目だけ）
                names = [c.text.strip()]
                t = things(spec).get(thing_of(lk.name))
                ty = next((f.type for f in thing_fields(t) if f.name == names[0]), None) if t is not None else None
                if ty is not None and ty not in NUMERIC:
                    out.append(Finding("E32", c.line, f"look {lk.name}: sum は数の項目だけです（{names[0]} は {ty}）"))
            for n in names:
                if flds and n not in flds:
                    out.append(Finding("E28", c.line, f"look {lk.name}: 「{n}」という項目はありません（{', '.join(sorted(flds))}）"))
    return out


# ---------------------------------------------------------------------------
# 29. rule の do が2つ以上（上から順に動く＝順序が生まれる）
# ---------------------------------------------------------------------------

def check_single_do(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    for r in rules(spec).values():
        dos = r.children_of("do")
        if len(dos) > 1:
            out.append(Finding("E29", dos[1].line, f"rule {r.name}: do は1つだけです。2つやりたい時は rule を分けて、relate の then でつなぐ（順序を書かない）"))
    return out


def check_roles(spec: Spec, opt: Options) -> list[Finding]:
    """who に書いた役割（admin など）は、thing User の role[...] の状態のどれか"""
    out = []
    u = things(spec).get("User")
    role = next((f for f in thing_fields(u) if f.name == "role" and f.states), None) if u else None
    known = set(role.states) if role else set()
    for w in spec.decls("who"):
        for c in w.children:
            r = c.raw.split()[0] if c.raw.split() else ""
            if r in ("user", "nobody") or r in known:
                continue
            hint = f"（{' / '.join(sorted(known))}）" if known else "。thing User に `role[member | " + r + "]` を書きます"
            out.append(Finding("E28", c.line, f"who: 「{r}」という役割がありません{hint}"))
    return out


# ---------------------------------------------------------------------------
# 31. do の書き方（動かす前に分かるように）
# ---------------------------------------------------------------------------

DO_FORMS = [f[0] for f in _DO_DOC if f[0] != r"(\w+) with (\w+)"]
_VALUE = re.compile("^(" + "|".join(f[0] for f in VALUE_FORMS) + ")$")


def check_do_form(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    ths = things(spec)
    verbs = {(c.name, " ".join(g.text.split()[:2])) for c in spec.decls("connect") for g in c.children if g.keyword == "does"}
    for r in rules(spec).values():
        for d in r.children_of("do"):
            t = d.text.strip()
            aw = re.fullmatch(r"(\w+) with (\w+)", t)
            if t in actions(spec) or (aw and aw.group(1) in actions(spec)) or any(re.fullmatch(f, t) for f in DO_FORMS):
                pass
            elif t.split() and (t.split()[0], " ".join(t.split()[1:3])) in verbs:
                pass
            else:
                import difflib
                head, _, rest = t.partition(" ")
                verb = difflib.get_close_matches(head, ["move", "notify", "remove", "go", "create", "set"], n=1, cutoff=0.6)
                hint = f"。もしかして `{verb[0]} {rest}`？" if verb and verb[0] != head else ""
                out.append(Finding("E31", d.line, f"rule {r.name}: do の書き方が分かりません: '{t}'（使えるのは notify / move / remove this / go / create / set 項目 to 値 / action の名前 [with 項目] / connect の does）{hint}"))
                continue
            sm = re.fullmatch(r"set \w+ to (.+)", t)
            if sm and not _VALUE.match(sm.group(1).strip()):
                out.append(Finding("E31", d.line, f"rule {r.name}: set の値の書き方が分かりません: '{sm.group(1)}'（result / this / me / \"文字\" / 7 days from now / {{名前}} / 項目 of this）"))
            m = re.fullmatch(r"create (\w+)", t)
            if m:
                if m.group(1) not in ths:
                    out.append(Finding("E28", d.line, f"rule {r.name}: 「{m.group(1)}」という thing はありません"))
                    continue
                flds = {f.name for f in thing_fields(ths[m.group(1)])}
                for c in d.children:
                    if c.keyword not in flds:
                        out.append(Finding("E28", c.line, f"create {m.group(1)}: 「{c.keyword}」という項目はありません（{', '.join(sorted(flds))}）"))
                    elif not _VALUE.match(c.text.strip()):
                        out.append(Finding("E31", c.line, f"create {m.group(1)}: 値の書き方が分かりません: '{c.text}'（this / me / \"文字\" / 7 days from now / {{名前}} / 項目 of this）"))
    return out


# ---------------------------------------------------------------------------
# 32. 型：rule ごとに this が何の thing かを決めて、項目と値の型を確かめる
# ---------------------------------------------------------------------------

NUMERIC = {"number", "count", "money", "percent"}


def list_thing(spec: Spec, name: str) -> str:
    seen = set()
    while spec.find("list", name) is not None and name not in seen:
        seen.add(name)
        of = spec.find("list", name).child("of")
        name = of.text.strip() if of is not None else name
    return name


def rule_this(spec: Spec) -> dict[str, str | None]:
    """rule → this の thing。when から決め、relate の then でつながる先へ渡す（create の後は作った箱）"""
    ths = things(spec)
    rs = rules(spec)
    this: dict[str, str | None] = {}
    for r in rs.values():
        w = r.child("when")
        t = None
        if w is not None:
            m = re.match(r"^user (?:taps|holds|swipes) \S+ on (\w+)", w.text.strip()) or \
                re.match(r"^(\w+) (?:is created|moves to \w+|is removed)$", w.text.strip())
            if m:
                t = list_thing(spec, m.group(1))
                t = t if t in ths else None
        this[r.name] = t

    def after(name):
        for d in rs[name].children_of("do"):
            m = re.fullmatch(r"create (\w+)", d.text.strip())
            if m:
                return m.group(1)
        return this[name]
    for _ in range(len(rs) + 1):                     # then の先へ、決まるまで渡す
        for a, rel, b, _ in relate_lines(spec):
            if rel == "then" and a in rs and b in rs and this[b] is None and after(a) is not None:
                this[b] = after(a)
    return this


def rule_result(spec: Spec) -> dict[str, str | None]:
    """rule → 直前の action の答えの型（then で渡る）"""
    rs, acts = rules(spec), actions(spec)
    res: dict[str, str | None] = {n: None for n in rs}

    def out_type(a):
        o = acts[a].child("out")
        for alt in (o.text.split("|") if o else []):
            w = alt.split()
            if len(w) >= 2:
                return w[1]
            if len(w) == 1 and w[0] in BUILTIN_TYPES:
                return w[0]
        return None
    for r in rs.values():
        for d in r.children_of("do"):
            name = d.text.strip().split()[0] if d.text.strip() else ""
            if name in acts:
                res[r.name] = out_type(name)
    for _ in range(len(rs) + 1):
        for a, rel, b, _ in relate_lines(spec):
            if rel == "then" and a in rs and b in rs and res[b] is None:
                res[b] = res[a]
    return res


def check_types(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    ths = things(spec)
    fields = {n: {f.name: f for f in thing_fields(t)} for n, t in ths.items()}
    this_of, result_of = rule_this(spec), rule_result(spec)

    def ftype(thing, name):
        f = fields.get(thing, {}).get(name)
        return None if f is None else ("state" if f.states else f.type)

    def value_type(expr, r, this):
        """値の式 → 型（分からなければ None）"""
        e = expr.strip()
        if e == "this":
            return this
        if e == "me":
            return "User"
        if e == "result":
            return result_of.get(r.name)
        if re.fullmatch(r"\d+ (minutes?|hours?|days?|weeks?) from now", e):
            return "monthday"
        m = re.fullmatch(r"(\w+) of this", e)
        if m and this:
            return ftype(this, m.group(1))
        if re.fullmatch(r'"-?\d+"|-?\d+', e):
            return "number"
        if re.fullmatch(r'".*"', e):
            return "text"
        return None

    def fits(want, got):
        if want is None or got is None or want == got:
            return True
        if want in ("text",):
            return got not in ths                       # 文字には何でも入る（別の箱は入らない）
        if want in NUMERIC:
            return got in NUMERIC
        if want in ("monthday", "date"):
            return got in ("monthday", "date")
        return False

    def need_this(r, d, this):
        if this is None:
            out.append(Finding("E32", d.line, f"rule {r.name}: this が何の thing か決まりません（when に `on 〇〇` か `〇〇 is created` を書くか、relate の then で前の rule からつなぐ）"))
            return False
        return True

    for l in spec.decls("list"):                   # list の where の項目も
        t = list_thing(spec, l.name)
        for w in l.children_of("where"):
            f = w.text.split()[0] if w.text.split() else ""
            if f != "it" and t in fields and f not in fields[t]:
                out.append(Finding("E32", w.line, f"list {l.name}: {t} に「{f}」という項目はありません（{', '.join(fields[t])}）"))
    for d in spec.decls("scene"):                  # stats の sum は数の項目だけ
        for c in d.walk():
            st = re.search(r"(?:^|\s)stats\s+(.+)$", c.raw) if c is not d else None
            for x in (st.group(1).split(",") if st else []):
                m = re.fullmatch(r"sum (\w+) of (\w+)", x.strip())
                if m:
                    t = list_thing(spec, m.group(2))
                    ty = ftype(t, m.group(1))
                    if ty is None or ty not in NUMERIC:
                        out.append(Finding("E32", c.line, f"stats: {t}.{m.group(1)} は{'ありません' if ty is None else f' {ty} で、足せません（数の項目だけ）'}"))
    for r in rules(spec).values():
        this = this_of[r.name]
        for w in r.children_of("where"):
            if not w.text.split():
                out.append(Finding("E31", w.line, f"rule {r.name}: where の中身がありません（`where status is todo` のように書く）"))
                continue
            f = w.text.split()[0]
            if f != "it" and this and f not in fields.get(this, {}):
                out.append(Finding("E32", w.line, f"rule {r.name}: {this} に「{f}」という項目はありません（{', '.join(fields[this])}）"))
        for d in r.children_of("do"):
            t = d.text.strip()
            m = re.fullmatch(r"move this to (\w+)", t)
            if m and need_this(r, d, this):
                sts = [x for f in fields[this].values() for x in (f.states or [])]
                if m.group(1) not in sts:
                    out.append(Finding("E32", d.line, f"rule {r.name}: {this} に「{m.group(1)}」という状態はありません（{' / '.join(sts)}）"))
            m = re.fullmatch(r"move (\w+) of this to (\w+)", t)
            if m and need_this(r, d, this):
                ref = ftype(this, m.group(1))
                if ref not in ths:
                    out.append(Finding("E32", d.line, f"rule {r.name}: {this}.{m.group(1)} は別の thing を指す項目ではありません"))
                else:
                    sts = [x for f in fields[ref].values() for x in (f.states or [])]
                    if m.group(2) not in sts:
                        out.append(Finding("E32", d.line, f"rule {r.name}: {ref} に「{m.group(2)}」という状態はありません（{' / '.join(sts)}）"))
            m = re.fullmatch(r"set (\w+) to (.+)", t)
            if m and need_this(r, d, this):
                want = ftype(this, m.group(1))
                if want is None:
                    out.append(Finding("E32", d.line, f"rule {r.name}: {this} に「{m.group(1)}」という項目はありません（{', '.join(fields[this])}）"))
                elif want == "state":
                    out.append(Finding("E32", d.line, f"rule {r.name}: {m.group(1)} は状態です。set ではなく move で動かします（flow を守るため）"))
                elif not fits(want, value_type(m.group(2), r, this)):
                    out.append(Finding("E32", d.line, f"rule {r.name}: {this}.{m.group(1)} は {want} なのに、{m.group(2).strip()} は {value_type(m.group(2), r, this)} です"))
            m = re.fullmatch(r"(\w+) with (\w+)", t)
            if m and m.group(1) in actions(spec) and need_this(r, d, this) and ftype(this, m.group(2)) is None:
                out.append(Finding("E32", d.line, f"rule {r.name}: {this} に「{m.group(2)}」という項目はありません（{', '.join(fields[this])}）"))
            m = re.fullmatch(r"create (\w+)", t)
            if m and m.group(1) in ths:
                for c in d.children:
                    want = ftype(m.group(1), c.keyword)
                    got = value_type(c.text, r, this)
                    if want is not None and want != "state" and not fits(want, got):
                        out.append(Finding("E32", c.line, f"create {m.group(1)}: {c.keyword} は {want} なのに、{c.text.strip()} は {got} です"))
            m = re.fullmatch(r'notify \w+ "(.*)"', t)
            if m and this:
                w = r.child("when")
                vars_ = set(re.findall(r"\{(\w+)\}", w.text)) if w is not None else set()
                for x in re.findall(r"\{(\w+)\}", m.group(1)):
                    if x not in fields[this] and x not in vars_:
                        out.append(Finding("E32", d.line, f"rule {r.name}: 通知の {{{x}}} が {this} の項目にも when の {{…}} にもありません"))
    return out


# ---------------------------------------------------------------------------
# 30. 通知の宛先が書いていない
# ---------------------------------------------------------------------------

_NOTIFY = re.compile(r'^notify\s+(\S+)\s+(each of \w+|".*")$')


def check_notify_recipient(spec: Spec, opt: Options) -> list[Finding]:
    out = []
    user_fields = {f.name for t in things(spec).values() for f in thing_fields(t)
                   if f.type in things(spec) and "name" in {x.name for x in thing_fields(things(spec)[f.type])} or f.type == "User"}
    for r in rules(spec).values():
        for d in r.children_of("do"):
            if not d.text.startswith("notify"):
                continue
            m = _NOTIFY.match(d.text)
            if not m:
                out.append(Finding("E30", d.line, f"rule {r.name}: 通知の宛先がありません（`notify me \"...\"` / `notify owner each of 一覧`）: '{d.text}'"))
            elif m.group(1) != "me" and m.group(1) not in user_fields:
                out.append(Finding("E30", d.line, f"rule {r.name}: 宛先「{m.group(1)}」は me か、人を指す項目の名前（{', '.join(sorted(user_fields)) or 'なし'}）です"))
    return out


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# example の中の値（動かす前に分かるもの）と、ログインに要る User.name
# ---------------------------------------------------------------------------

STEPS = ("given", "adds", "at", "says", "taps", "gets", "expect")
WHO_VERBS = ("see", "change", "create", "remove", "move", "do")
SLOTS = ("top", "main", "side", "bottom", "over")
CLAUSES = {"rule": ("why", "when", "where", "do", "example"),
           "list": ("of", "where", "sort"),
           "action": ("in", "out", "example", "never", "else", "by", "ask", "how", "do"),
           "part": ("in", "do", "show", "mark"),
           "connect": ("gives", "needs", "does", "limit"),
           "look": ("title", "sub", "mark", "lead", "image", "button", "empty", "heading", "search", "group", "take", "sum")}


def check_example_values(spec: Spec, opt: Options) -> list[Finding]:
    """動かす前に分かる、行の形の間違い（example の手順・flow・list の where と sort・notify each of）"""
    from .values import _DUR, parse_time, unquote
    out = []
    ths_all, list_names = things(spec), {l.name for l in spec.decls("list")}
    # who の行の打ち間違い（読めない行は黙って無視され、書いたつもりの権利が無くなる）
    for w in spec.decls("who"):
        for c in w.children:
            m = re.match(r"^(\w+)\s+(\w+)\s+(\w+)\s+(\w+)(?:\s+where\s+.+)?$", c.raw.strip())
            if not m or m.group(2) != "can":
                word = m.group(2) if m else ""
                out.append(Finding("E28", c.line, f"who: 読めません: '{c.raw.strip()}'（`user can see Task where owner is me` の形）{did_you_mean(word, ['can']) if word else ''}"))
                continue
            if m.group(3) not in WHO_VERBS:
                out.append(Finding("E28", c.line, f"who: 「{m.group(3)}」はできることの名前ではありません（{' / '.join(WHO_VERBS)}）{did_you_mean(m.group(3), WHO_VERBS)}"))
    # 画面の置き場所の打ち間違い（`mian` だと、その部品が黙って出ない）
    for sc in spec.decls("scene"):
        for c in sc.children:
            if c.text.startswith("["):
                continue
            if c.keyword not in SLOTS:
                out.append(Finding("E28", c.line, f"scene {sc.name}: 「{c.keyword}」という置き場所はありません（{' / '.join(SLOTS)}）{did_you_mean(c.keyword, SLOTS)}"))
    # flow の状態の打ち間違い（`otdo -> done` だと、黙って新しい状態ができ、始まりの状態まで変わる）
    for f in spec.decls("flow"):
        m = re.fullmatch(r"(\w+)\.(\w+)", f.name or "")
        if not m or m.group(1) not in ths_all:
            continue
        fld = next((x for x in thing_fields(ths_all[m.group(1)]) if x.name == m.group(2)), None)
        if fld is None or not fld.states:
            continue
        try:
            edges, wins = flow_parts(f)
        except ParseError:
            continue
        for st in dict.fromkeys([x for e in edges + wins for x in e if x]):
            if st not in fld.states:
                out.append(Finding("E18", f.line, f"flow {f.name}: 「{st}」は {f.name} の状態にありません（{' / '.join(fld.states)}）{did_you_mean(st, fld.states)}"))
    # input の項目の打ち間違い（どの thing にも合わないと、画面を開いた時に止まる）
    all_fields = {n: [x.name for x in thing_fields(t)] for n, t in ths_all.items()}
    for inp in spec.decls("input"):
        names = [c.keyword for c in inp.children]
        if names and not any(set(names) <= set(fs) for fs in all_fields.values()):
            best = max(all_fields, key=lambda n: len(set(names) & set(all_fields[n])), default=None)
            for c in inp.children:
                if best and c.keyword not in all_fields[best]:
                    out.append(Finding("E28", c.line, f"input {inp.name}: {best} に「{c.keyword}」という項目はありません（{', '.join(all_fields[best])}）{did_you_mean(c.keyword, all_fields[best])}"))
    # example の箱の中身の項目の打ち間違い
    for r in rules(spec).values():
        for ex in r.children_of("example"):
            for c in ex.children:
                if c.keyword not in ("given", "adds", "taps", "expect") or not c.children:
                    continue
                w = c.text.split()
                thing = w[2] if c.keyword == "taps" and len(w) >= 3 else (w[0] if w else "")
                if thing not in all_fields:
                    continue
                for v in c.children:
                    if v.keyword not in all_fields[thing]:
                        out.append(Finding("E32", v.line, f"rule {r.name}: {thing} に「{v.keyword}」という項目はありません（{', '.join(all_fields[thing])}）{did_you_mean(v.keyword, all_fields[thing])}"))
    # 節の打ち間違い（`wher status is todo` が黙って無視されると、条件の無い rule になってしまう）
    for kind, allowed in CLAUSES.items():
        for d in spec.decls(kind):
            for c in d.children:
                if c.keyword not in allowed:
                    out.append(Finding("E28", c.line, f"{kind} {d.name}: 「{c.keyword}」という節はありません（{' / '.join(allowed)}）{did_you_mean(c.keyword, allowed)}"))
    for f in spec.decls("flow"):
        if f.name == "scene":
            continue
        try:
            edges, _ = flow_parts(f)
        except ParseError:
            continue
        if not edges:
            out.append(Finding("E28", f.line, f"flow {f.name}: 矢印（`a -> b`）が1つもありません"))
        elif any(not a or not b for a, b in edges):
            out.append(Finding("E28", f.line, f"flow {f.name}: 矢印の片側が空です（`a -> b` の両側に状態を書く）"))
    for l in spec.decls("list"):
        so = l.child("sort")
        if so is not None and not so.text.split():
            out.append(Finding("E28", so.line, f"list {l.name}: sort の後ろに項目がありません（`sort deadline`）"))
        for w in l.children_of("where"):
            m = re.match(r"^\w+ within (.+)$", w.text.strip())
            if m and not _DUR.match(m.group(1).strip()):
                out.append(Finding("E32", w.line, f"list {l.name}: 期間が読めません: {m.group(1)}（`3 days` / `12 hours` のように書く）"))
    for r in rules(spec).values():
        for d in r.children_of("do"):
            m = re.match(r"^notify \w+ each of (\w+)$", d.text.strip())
            if m and m.group(1) not in list_names:
                out.append(Finding("E28", d.line, f"rule {r.name}: each of の「{m.group(1)}」という list がありません"))
    for r in rules(spec).values():
        for ex in r.children_of("example"):
            for c in ex.children:
                t = c.text.strip()
                bad = None
                if c.keyword not in STEPS:
                    bad = f"example に「{c.keyword}」という手順はありません（{' / '.join(STEPS)}）"
                elif c.keyword in ("given", "adds") and (not t or t.split()[0] not in ths_all):
                    bad = f"{c.keyword} の後ろには thing の名前を書きます: '{c.raw.strip()}'"
                elif c.keyword == "taps" and not re.match(r"^\S+ on \w+$", t):
                    bad = f"taps は `taps ボタン on Thing` と書きます: '{c.raw.strip()}'"
                elif c.keyword == "says" and not re.fullmatch(r'"[^"]*"', t):
                    bad = f'says は `says "文"` と書きます: \'{c.raw.strip()}\''
                elif c.keyword == "gets" and not re.match(r'^(\w+) (.+?) "(.*)"$', t):
                    bad = f'gets は `gets Gmail new message "本文"` と書きます: \'{c.raw.strip()}\''
                elif c.keyword == "expect" and not t:
                    bad = "expect の後ろに、確かめることを書きます"
                if bad:
                    out.append(Finding("E31", c.line, f"rule {r.name}: {bad}"))
    ths = things(spec)
    if "User" in ths and "name" not in {f.name for f in thing_fields(ths["User"])}:
        out.append(Finding("E28", ths["User"].line, "thing User: ログインした人の名前を入れる `name text` が要ります"))
    fields = {n: {f.name: f for f in thing_fields(t)} for n, t in ths.items()}
    for d in rules(spec).values():
        for ex in d.children_of("example"):
            for c in ex.children:
                if c.keyword == "at":
                    try:
                        parse_time(unquote(c.text), 2000)
                    except ValueError:
                        out.append(Finding("E32", c.line, f"rule {d.name}: at の日時が読めません: {c.text.strip()}（`at \"9/21 21:00\"` のように書く）"))
                    continue
                if c.keyword not in ("given", "adds", "taps", "expect"):
                    continue
                words = c.text.split()
                thing = words[2] if c.keyword == "taps" and len(words) >= 3 else (words[0] if words else "")
                for v in c.children:
                    f = fields.get(thing, {}).get(v.keyword)
                    if f is None or f.type not in ("date", "monthday") or not v.text.strip():
                        continue
                    try:
                        parse_time(unquote(v.text), 2000)
                    except ValueError:
                        out.append(Finding("E32", v.line, f"rule {d.name}: {thing}.{v.keyword} は {f.type} ですが、日時として読めません: {v.text.strip()}"))
    return out


ALL_CHECKS = [
    check_match_else, check_until_limit, check_examples, check_else, check_tbd,
    check_blocking, check_when_is_event, check_move_narrowed, check_flow_coverage,
    check_conflict, check_list_cycle, check_nesting, check_contract,
    check_relate_cycle, check_relate_contradiction, check_before_possible,
    check_double_else, check_match_states, check_who, check_gone, check_change,
    check_ask_ai_limit, check_connect_fallback, check_scene_move, check_words,
    check_a11y, check_money, check_undefined, check_single_do, check_do_form, check_roles, check_types, check_notify_recipient,
    check_example_values,
]


def did_you_mean(name: str, candidates, form: str = "。もしかして {}？") -> str:
    """打ち間違いらしい時だけ、近い名前を1つ出す（大文字小文字の違い・1〜2文字の違い）"""
    import difflib
    cands = [c for c in candidates if c and c != name]
    same = [c for c in cands if c.lower() == name.lower()]
    hit = same or difflib.get_close_matches(name, cands, n=1, cutoff=0.75)
    return form.format(hit[0]) if hit else ""


_NAMED = re.compile(r"「([^」]+)」という(?:状態|項目)はありません（([^）]*)）")


def _with_suggestion(f: Finding) -> Finding:
    """「X」という状態／項目はありません（a / b）に、近い名前があれば「もしかして」を足す"""
    m = _NAMED.search(f.message)
    if not m:
        return f
    hint = did_you_mean(m.group(1), re.split(r"\s*/\s*|,\s*", m.group(2)))
    return Finding(f.code, f.line, f.message + hint) if hint else f


def check(spec: Spec, opt: Options | None = None) -> list[Finding]:
    opt = opt or Options()
    found: list[Finding] = []
    for fn in ALL_CHECKS:
        try:
            found.extend(fn(spec, opt))
        except ParseError as e:           # 行が読めない（`sub` だけの項目など）。同じ行は1回だけ出す
            if not any(f.line == e.line and f.message == e.message for f in found):
                found.append(Finding("E31", e.line, e.message))
    found = [_with_suggestion(f) for f in found]
    found.sort(key=lambda f: (f.line, f.code))
    return found
