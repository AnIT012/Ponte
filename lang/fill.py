"""by ai の穴埋め（仕様 v0.2 12章 ビルド手順 4・5）。

  AIに契約（in / out / example / never / else）を渡す
  → AIが do（とshape）を書く
  → 読めるか・チェッカー・全部の example・never を機械で確かめる
  → 通らなければ、何がダメだったかをそのままAIに返して書き直させる（上限回数まで）
  → 通ったら <spec>.ai/<action>.lang に残す。人も読めて、直してもいい

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

DO_GUIDE = """\
# この言語の action の中身（do）の書き方

do に書けるのは次の2つだけ。if・for・ループ・再帰・書き換え・true/false はありません。
- `名前 = 式`
- `名前[状態a | 状態b] = match 式` と、その下に字下げした枝 `値 -> 結果`（最後に `else -> 結果`。宣言した状態を全部書けば else は省略可）

決まり:
- 行の順番は関係ない。名前の依存で決まる。同じ名前を2回書けない。
- 答えは「他のどの行からも使われていない行」。ちょうど1つにする。答えの行に `[...]` は付けなくていい（形は out に書いてある）。
- 状態の名前（`kind[one | none | many]` の one など）は、値を持たない名前だけ。`found 値` のように値を持つのは out の状態だけ。
- match の中に match は書けない。一度名前を付けて、別の行で match する。
- 入力は `in` に書かれた名前で使える。
- 答えは out の形にする。out が `found monthday | missing` なら、`found 値` か `missing`。

契約の never のうち、機械が確かめるもの:
- `never guess the year`: 答えに年（4桁の数）を入れない
- `never depend on width`: 全角と半角で答えを変えない（全角にした例も同じ答えになるか確かめる。normalize を使うとよい）
- `never return empty`: 値が空の答えを返さない
- `never fail`: どんな入力でも止まらない（おかしな入力でも missing などを返す）

使える道具:
- 文字: normalize X（全角→半角など） / trim X / lower X / upper X / split X by "," / join X by "," / replace "a" with "b" in X
- 形: find all 形の名前 in X（形に当たったものを全部、集まりで返す）
- 集まり: count of X / first of X / last of X
- 日時: monthday of X（month・day・hour・minute を取り出した形の結果 → "10/15 12:00"）
- 数: number of X / a + b / a - b

形（shape）は正規表現の代わり。行頭に書く見出しで、1行に1つずつ並べる:
    shape 名前
      month  digits 1..2      # 名前 digits 範囲 で数字を取り出す
      "/"                     # そのままの文字
      maybe  "(" any 1 ")"    # あっても無くてもいい
      maybe  space            # 空白があっても無くてもいい
使える部品: "文字" / space / digits N / digits a..b / letters a..b / any a..b / word a..b / maybe ...

見本:
    do
      clean = normalize mail
      hits  = find all Price in clean
      kind[one | none | many] = match count of hits
                                  1    -> one
                                  0    -> none
                                  else -> many
      price = match kind
                one  -> found number of first of hits
                none -> missing
                many -> missing

    shape Price
      "¥"
      amount digits 1..7
"""

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
            problems.append(f"example L{ex.line}: {left} で止まりました: {e}")
            continue
        if not same(got, want):
            problems.append(f"example L{ex.line}: {left} → {right} のはずが {got}")
    problems += check_nevers(a, body, in_name)
    return Verdict(not problems, problems, mini_src)


def to_fullwidth(text: str) -> str:
    """半角の英数字と記号を全角にする（never depend on width の確かめに使う）"""
    return "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in text)


MACHINE_NEVERS = {"guess the year", "depend on width", "return empty", "fail"}
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
    return (DO_GUIDE + "\n# 書いてほしい action の契約（変えないでください）\n\n```\n" + action_source(spec, action)
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
            res.path = os.path.join(ai_dir(spec), f"{action.name}.lang")
            with open(res.path, "w", encoding="utf-8") as f:
                f.write(f"# action {action.name} の中身（by ai）。人も読めて、直してもいい。直したら python -m lang test で確かめる\n")
                f.write(f"# 書いたもの: {label or 'AI'}   試した回数: {i}   日時: {datetime.now().isoformat(timespec='minutes')}\n\n")
                f.write(code.strip() + "\n")
            res.ok = True
            return res
        messages.append({"role": "user", "content": feedback_prompt(v.problems)})
    return res


def load_body(spec: Spec, action: Node):
    """by ai → <spec>.ai/<名前>.lang、by code "x.lang" → spec と同じ場所の x.lang。無ければ None。"""
    by = action.child("by")
    if by is None:
        return None
    m = re.match(r'^code\s+"([^"]+)"$', by.text.strip())
    if m:
        path = os.path.join(os.path.dirname(spec.path), m.group(1))
    elif by.text.strip() == "ai":
        path = os.path.join(ai_dir(spec), f"{action.name}.lang")
    else:
        return None
    if not os.path.exists(path):
        return None
    code = open(path, encoding="utf-8").read()
    mini = parse(combine(action_source(spec, action), code))
    a = mini.find("action", action.name)
    return body_of(a, a.child("do"), {s.name: s for s in mini.decls("shape")})
