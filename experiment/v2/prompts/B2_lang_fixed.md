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

# 書いてほしい action の契約（変えないでください）

```
action ExtractDeadline
  in      mail text
  out     found monthday | missing
  example "10/15(木)12:00まで"            -> found 10/15 12:00
  example "【締切9/24 23:59】"            -> found 9/24 23:59
  example "来週中にご提出ください"        -> missing
  example "9/24 23:59 または 9/30 23:59"  -> missing
  never   guess the year
  never   depend on width
  else    ask user
  by      ai
```

返事は ```lang のコードブロック1つだけにしてください。中身は行頭の `do` の塊と、使う shape です。説明は要りません。

要件に書いていないことや矛盾があって決められない場合は、コードブロックの前に `Q: ...` の形で1行ずつ書いてください。
