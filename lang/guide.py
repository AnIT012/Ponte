"""AIに渡す「書き方の説明」を、実装から作る（手で書かない。実装とずれないように）。

  python -m lang guide              action の中身（do）の書き方を出す（AIに渡すのと同じもの）
  python -m lang guide --spec       仕様書 10章の道具の表を、今の実装に合わせて書き直す

元になるもの:
  - 道具と shape の部品 … lang/body.py の TOOLS / SHAPE_PARTS（1つずつ動く例付き）
  - 機械で確かめる never … lang/fill.py の MACHINE_NEVERS
  - 見本 … lang/std/ の中身（lang test で通っているもの）をそのまま載せる
"""
from __future__ import annotations

import os
import re

from .body import SHAPE_PARTS, TOOLS
from .parser import STD_DIR

RULES = """\
do に書けるのは次の2つだけ。if・for・ループ・再帰・書き換え・true/false はありません。
- `名前 = 式`
- `名前[状態a | 状態b] = match 式` と、その下に字下げした枝 `値 -> 結果`（最後に `else -> 結果`。宣言した状態を全部書けば else は省略可。数の範囲 `1..3` / `..-1` / `4..` も枝に書ける）

決まり:
- 行の順番は関係ない。名前の依存で決まる。同じ名前を2回書けない。
- 答えは「他のどの行からも使われていない行」。ちょうど1つにする。答えの行に `[...]` は付けなくていい（形は out に書いてある）。
- 状態の名前（`kind[one | none | many]` の one など）は、値を持たない名前だけ。`found 値` のように値を持つのは out の状態だけ。
- 状態の名前と行の名前を同じにしない（どちらか分からないのでエラー）。
- match の中に match は書けない。一度名前を付けて、別の行で match する。
- 入力は `in` に書かれた名前で使える。
- 答えは out の形にする。out が `found monthday | missing` なら、`found 値` か `missing`。"""

SAMPLE = "FindMonthDay"     # 見本に載せる std の中身（テストで通っているもの）


def tools_table() -> str:
    rows = ["| 種類 | 書き方 | 意味 | 例 |", "|---|---|---|---|"]
    for kind, form, meaning, expr, inp, want in TOOLS:
        ex = f"`{expr}`（t が \"{inp}\" なら {want!r}）" if expr else "—"
        rows.append(f"| {kind} | `{form}` | {meaning} | {ex} |")
    return "\n".join(rows)


def shape_table() -> str:
    return "\n".join(f"- `{form}` … {meaning}" for form, meaning in SHAPE_PARTS)


def sample() -> str:
    path = os.path.join(STD_DIR, "body", f"{SAMPLE}.lang")
    code = open(path, encoding="utf-8").read()
    code = "\n".join(l for l in code.splitlines() if not l.startswith("#")).strip()
    return code


def do_guide() -> str:
    from .fill import MACHINE_NEVERS
    nevers = "\n".join(f"- `never {k}`: {v}" for k, v in MACHINE_NEVERS.items())
    return f"""# この言語の action の中身（do）の書き方

{RULES}

契約の never のうち、機械が確かめるもの:
{nevers}

使える道具（これ以外は無い。無い道具を書くとエラーになる）:
{tools_table()}

形（shape）は正規表現の代わり。行頭に書く見出しで、下に部品を1行に1つずつ並べる:
{shape_table()}

見本（std/date の FindMonthDay。`lang test` で通っているもの）:
```
{sample()}
```
"""


SPEC_BEGIN = "<!-- 自動: python -m lang guide --spec（ここから） -->"
SPEC_END = "<!-- 自動（ここまで） -->"


def spec_block() -> str:
    return f"""{SPEC_BEGIN}
今ある道具（実装から作った表。例は全部テストで動かしている）:

{tools_table()}

shape の部品:

{shape_table()}
{SPEC_END}"""


def write_spec(path: str) -> bool:
    """仕様書の自動の所を書き直す。変わったら True"""
    text = open(path, encoding="utf-8").read()
    if SPEC_BEGIN not in text:
        raise ValueError(f"{path} に {SPEC_BEGIN} がありません")
    new = re.sub(re.escape(SPEC_BEGIN) + r".*?" + re.escape(SPEC_END), lambda m: spec_block(), text, flags=re.S)
    if new != text:
        open(path, "w", encoding="utf-8").write(new)
    return new != text
