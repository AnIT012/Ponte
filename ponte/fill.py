"""by ai の穴埋め（仕様 v0.2 12章 ビルド手順 4・5）。

  AIに契約（in / out / example / never / else）を渡す
  → AIが do（とshape）を書く
  → 読めるか・チェッカー・全部の example・never を機械で確かめる
  → 通らなければ、何がダメだったかをそのままAIに返して書き直させる（上限回数まで）
  → 通ったら <spec>.ai/<action>.ponte に残す。人も読めて、直してもいい

AIの呼び出しは Python 標準の urllib で Anthropic API を直接叩く（ライブラリに依存しないため）。
キーが無い時は、用意した返事のファイルを AI の代わりに使える（--ai file:返事.md）。
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime

from .body import BodyError, Tagged, body_of, out_states_of, parse_expected, same
from .checker import check
from .parser import Node, ParseError, Spec, parse
from .values import unquote



SYSTEM = "あなたはこの言語の action の中身を書くプログラマーです。契約（in / out / example / never / else）は変えずに、do だけを書きます。"


# ---------------------------------------------------------------------------
# 返事を読む
# ---------------------------------------------------------------------------

def extract_code(reply: str) -> str | None:
    m = re.search(r"```[a-zA-Z]*\n(.*?)```", reply, re.S)
    return m.group(1) if m else None


def action_source(spec: Spec, action: Node) -> str:
    """spec の中の action の行（中身の do は除く）"""
    lines = spec.lines
    start = action.line - 1
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or lines[end].startswith(" ")):
        end += 1
    kept, skip_indent = [], None
    for l in lines[start:end]:
        ind = len(l) - len(l.lstrip())
        if skip_indent is not None:
            if l.strip() and ind <= skip_indent:
                skip_indent = None
            else:
                continue
        if l.strip() == "do":
            skip_indent = ind
            continue
        kept.append(l)
    return "\n".join(kept).rstrip() + "\n"


def normalize_reply(code: str) -> str:
    """返事の形のゆれを揃える。契約（action の行）まで書き写して、do と shape を字下げの中に入れてきた返事も読めるようにする。
    中身は変えない。行頭に do / shape を出して、字下げを戻すだけ。"""
    lines = code.splitlines()
    if not any(l.startswith("action ") for l in lines):
        return code
    out, i = [], 0
    while i < len(lines):
        l = lines[i]
        head = l.strip()
        ind = len(l) - len(l.lstrip())
        if head == "do" or head.startswith("shape "):
            out.append(head)
            i += 1
            while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > ind):
                out.append(lines[i][ind:] if lines[i].strip() else "")
                i += 1
            continue
        i += 1          # 契約の行（action / in / out / example ...）は捨てる。契約は spec の方を使う
    return "\n".join(out) + "\n"


def combine(action_src: str, code: str) -> str:
    """action の契約 + AIの do + shape → 1つの小さな spec"""
    code = normalize_reply(code)
    do_lines, rest, in_do = [], [], False
    for l in code.splitlines():
        if l.strip() == "do" and not l.startswith(" "):
            in_do = True
            continue
        if in_do and (not l.strip() or l.startswith(" ")):
            do_lines.append(l)
            continue
        in_do = False
        rest.append(l)
    if not any(l.strip() for l in do_lines):
        raise ParseError(1, "返事に `do` の塊がありません（行頭に do、その下に字下げして書く）")
    body = "\n".join(("  " + l) if l.strip() else "" for l in do_lines)
    return action_src + "  do\n" + body.rstrip() + "\n\n" + "\n".join(rest).strip() + "\n"


# ---------------------------------------------------------------------------
# 確かめる
# ---------------------------------------------------------------------------

@dataclass
class Verdict:
    ok: bool
    problems: list[str]
    source: str = ""


CHECK_CODES = {"E01", "E12", "E18"}


def verify(spec: Spec, action: Node, code: str) -> Verdict:
    try:
        mini_src = combine(action_source(spec, action), code)
        mini = parse(mini_src)
    except ParseError as e:
        return Verdict(False, [f"読めません: {e}"])
    problems = [f"チェッカー: {f}" for f in check(mini) if f.code in CHECK_CODES]
    a = mini.find("action", action.name)
    shapes = {s.name: s for s in mini.decls("shape")}
    try:
        body = body_of(a, a.child("do"), shapes)
    except BodyError as e:
        return Verdict(False, problems + [f"do: {e}"], mini_src)
    outs = out_states_of(a)
    in_name = a.child("in").text.split()[0]
    for ex in a.children_of("example"):
        left, right = [x.strip() for x in ex.text.split("->", 1)]
        want = parse_expected(right, outs)
        try:
            got = body.run({in_name: unquote(left)})
        except (BodyError, Exception) as e:
            if isinstance(e, BodyError) and any(str(e) in p for p in problems):
                continue                     # 同じ行の同じ間違いは1回だけ言う（どの例でも同じなので）
            problems.append(f"example L{ex.line}: {left} で止まりました: {e}")
            continue
        if not same(got, want):
            problems.append(f"example L{ex.line}: {left} → {right} のはずが {got}")
    problems += check_nevers(a, body, in_name)
    return Verdict(not problems, problems, mini_src)


def to_fullwidth(text: str) -> str:
    """半角の英数字と記号を全角にする（never depend on width の確かめに使う）"""
    return "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in text)


MACHINE_NEVERS = {                      # 機械で確かめる never（説明は ponte guide にもそのまま出る）
    "guess the year": "答えに年（4桁の数）を入れない",
    "depend on width": "全角と半角で答えを変えない（全角にした例も同じ答えになるか確かめる。normalize を使うとよい）",
    "return empty": "値が空の答えを返さない",
    "fail": "どんな入力でも止まらない（おかしな入力でも missing などを返す）",
}
FUZZ = ["", " ", "あ", "12:00", "13/45 99:99", "1/1", "締切", "0/0 0:00", "🙂" * 30, "x" * 2000, "\n\t", "９／９ ９：００"]


def check_nevers(a: Node, body, in_name: str) -> list[str]:
    """never を機械で確かめられるものだけ確かめる。確かめられないものは確かめない（正直な限界）。"""
    out = []
    for n in a.children_of("never"):
        if n.text.strip() == "depend on width":
            for ex in a.children_of("example"):
                src = unquote(ex.text.split("->", 1)[0])
                wide = to_fullwidth(src)
                if wide == src:
                    continue
                try:
                    got, got_w = body.run({in_name: src}), body.run({in_name: wide})
                except Exception as e:     # noqa: BLE001
                    out.append(f"never depend on width: 全角にした「{wide}」で止まりました: {e}")
                    continue
                if str(got) != str(got_w):
                    out.append(f"never depend on width: 「{src}」は {got} なのに、全角の「{wide}」は {got_w} でした")
            continue
        if n.text.strip() == "return empty":
            for p_in in [unquote(ex.text.split("->", 1)[0]) for ex in a.children_of("example")] + FUZZ:
                try:
                    got = body.run({in_name: p_in})
                except Exception:          # noqa: BLE001  止まるのは never fail の方で見る
                    continue
                v = got.value if isinstance(got, Tagged) else got
                if (isinstance(got, Tagged) and got.value is not None and str(v).strip() == "") or (not isinstance(got, Tagged) and str(v).strip() == ""):
                    out.append(f"never return empty: 「{p_in[:20]}」で空の答え {got!r} を返しました")
                    break
            continue
        if n.text.strip() == "fail":
            for p_in in FUZZ:
                try:
                    body.run({in_name: p_in})
                except Exception as e:     # noqa: BLE001
                    out.append(f"never fail: 「{p_in[:20]}」で止まりました（{e}）。止まらずに else の状態（missing など）を返す")
                    break
            continue
        if "year" in n.text:
            probes = [unquote(ex.text.split("->", 1)[0]) for ex in a.children_of("example")]
            probes += ["締切は10/15です", "3/1 9:00 締切", "12/31 23:59まで"]
            for p in probes:
                try:
                    got = body.run({in_name: p})
                except Exception:
                    continue
                if re.search(r"\b\d{4}\b", str(got.value if isinstance(got, Tagged) else got)):
                    out.append(f"never {n.text}: 「{p}」で年の入った答え {got} を返しました")
    return out


# ---------------------------------------------------------------------------
# AI
# ---------------------------------------------------------------------------

class AnthropicHTTP:
    """Anthropic Messages API を urllib で呼ぶ。"""
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, model: str = "claude-opus-5", effort: str = "high"):
        self.model, self.effort = model, effort
        self.key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.key:
            raise RuntimeError("ANTHROPIC_API_KEY がありません（--ai file:返事.md で AI の代わりの返事を使えます）")

    def __call__(self, messages: list[dict]) -> str:
        body = {
            "model": self.model,
            "max_tokens": 16000,
            "system": SYSTEM,
            "messages": messages,
            "output_config": {"effort": self.effort},
            "fallbacks": "default",          # 安全の仕組みで断られた時は、別のモデルで続ける
        }
        req = urllib.request.Request(self.URL, json.dumps(body).encode(), {
            "x-api-key": self.key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "server-side-fallback-2026-07-01",
            "content-type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"API エラー {e.code}: {e.read().decode(errors='replace')[:500]}")
        if data.get("stop_reason") == "refusal":
            raise RuntimeError(f"AIが断りました: {data.get('stop_details')}")
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


class FileAI:
    """AIの代わりに、用意した返事を順に返す。ファイル1つか、1.md 2.md ... の入ったフォルダ。"""

    def __init__(self, path: str):
        if os.path.isdir(path):
            self.replies = [open(os.path.join(path, f), encoding="utf-8").read()
                            for f in sorted(os.listdir(path), key=lambda x: int(re.sub(r"\D", "", x) or 0))]
        else:
            self.replies = [open(path, encoding="utf-8").read()]
        self.i = 0

    def __call__(self, messages):
        if self.i >= len(self.replies):
            raise RuntimeError("用意した返事を使い切りました")
        r = self.replies[self.i]
        self.i += 1
        return r


# ---------------------------------------------------------------------------
# ループ
# ---------------------------------------------------------------------------

@dataclass
class FillResult:
    action: str
    ok: bool
    tries: int
    history: list[list[str]] = field(default_factory=list)   # 各回の問題
    path: str | None = None


def first_prompt(spec: Spec, action: Node) -> str:
    from .guide import do_guide
    return (do_guide() + "\n# 書いてほしい action の契約（変えないでください）\n\n```\n" + action_source(spec, action)
            + "```\n\n返事は ```lang のコードブロック1つだけにしてください。中身は行頭の `do` の塊と、使う shape です。説明は要りません。")


def feedback_prompt(problems: list[str]) -> str:
    return "機械で確かめたら通りませんでした。直して、同じ形（```lang のブロック1つ）で全部書き直してください。\n" + "\n".join(f"- {p}" for p in problems)


def ai_dir(spec: Spec) -> str:
    return spec.path + ".ai"


def fill_action(spec: Spec, action: Node, ai, tries: int = 5, label: str = "") -> FillResult:
    messages = [{"role": "user", "content": first_prompt(spec, action)}]
    res = FillResult(action.name, False, 0)
    for i in range(1, tries + 1):
        reply = ai(messages)
        messages.append({"role": "assistant", "content": reply})
        res.tries = i
        code = extract_code(reply)
        v = verify(spec, action, code) if code is not None else Verdict(False, ["返事に ```lang のコードブロックがありません"])
        res.history.append(v.problems)
        if v.ok:
            os.makedirs(ai_dir(spec), exist_ok=True)
            res.path = os.path.join(ai_dir(spec), f"{action.name}.ponte")
            with open(res.path, "w", encoding="utf-8") as f:
                f.write(f"# action {action.name} の中身（by ai）。人も読めて、直してもいい。直したら python -m ponte test で確かめる\n")
                f.write(f"# 書いたもの: {label or 'AI'}   試した回数: {i}   日時: {datetime.now().isoformat(timespec='minutes')}\n\n")
                f.write(code.strip() + "\n")
            res.ok = True
            return res
        messages.append({"role": "user", "content": feedback_prompt(v.problems)})
    return res


def body_path(spec: Spec, action: Node) -> str | None:
    """by code "x.ponte" / by ai の中身が置かれるファイル。by が無い（その場の do）か、ほかの by なら None。"""
    by = action.child("by")
    if by is None:
        return None
    m = re.match(r'^code\s+"([^"]+)"$', by.text.strip())
    if m:
        return os.path.join(os.path.dirname(spec.where(action.line)[0]), m.group(1))   # use で読んだ action は、そのファイルから
    if by.text.strip() == "ai":
        return os.path.join(ai_dir(spec), f"{action.name}.ponte")
    return None


class ConfirmError(Exception):
    """宣言した値と、下の層が実際に使った値が違う（または報告がない）"""


class PythonBody:
    """`by python "x.py"`: 中身を下の層（Python）で書いた action。x.py の `answer(value, settings)` を呼ぶ。
    答えは example の右側と同じ書き方の文字（`found 10/15`、`missing` など）で返す。
    1回呼ぶたびに、`confirm` の名前を下の層が報告した値と照合する（仕様 5章 with と confirm）。"""

    def __init__(self, action: Node, path: str):
        import importlib.util
        from .body import out_states_of
        spec_ = importlib.util.spec_from_file_location(f"ponte_body_{action.name}", path)
        mod = importlib.util.module_from_spec(spec_)
        spec_.loader.exec_module(mod)
        if not hasattr(mod, "answer"):
            raise ValueError(f"{os.path.basename(path)} に answer(value, settings) がありません")
        self.fn, self.outs, self.name = mod.answer, out_states_of(action), action.name
        from .confirm import parts
        self.settings, self.raw, self.confirm = parts(action)

    def run(self, inputs: dict) -> object:
        from .body import parse_expected
        from .confirm import problems
        from .report import collect
        value = next(iter(inputs.values()), None)
        with collect() as got:
            ans = self.fn(value, dict(self.settings))
        bad = problems(self.settings, self.confirm, got, self.raw)
        if bad:
            raise ConfirmError("; ".join(bad))
        return parse_expected(str(ans), self.outs)


def load_body(spec: Spec, action: Node):
    """by が無く do がある → その do。by ai → <spec>.ai/<名前>.ponte、by code "x.ponte" → spec と同じ場所の x.ponte。無ければ None。"""
    by = action.child("by")
    if by is None:
        do = action.child("do")                  # 中身をその場に書いた action（AI も別ファイルも使わない）
        if do is None:
            return None
        return body_of(action, do, {s.name: s for s in spec.decls("shape")})
    by = action.child("by")
    m = re.match(r'^python\s+"([^"]+)"$', by.text.strip()) if by is not None else None
    if m:                                        # 下の層（Python）で書いた中身
        path = os.path.join(os.path.dirname(spec.where(action.line)[0]), m.group(1))
        return PythonBody(action, path) if os.path.exists(path) else None
    path = body_path(spec, action)
    if path is None or not os.path.exists(path):
        return None
    code = open(path, encoding="utf-8").read()
    mini = parse(combine(action_source(spec, action), code))
    a = mini.find("action", action.name)
    return body_of(a, a.child("do"), {s.name: s for s in mini.decls("shape")})
