# 全体案 — 足りないものを全部考えたもの（まだ合意していない）

`DESIGN_v0.2.md` の決まりを前提にした案。全部「案」で、確定は相談してから。
各項目の最後に「決めたいこと」を置いた。

前提のおさらい:
thing / flow（`>` で勝ち）/ list / match / rule / relate（then, then no, before, >, else）/ action（in, out, example, never, else, by, how, do）/ group / tbd / `##` / 状態は `[a | b]` / 項目は `名前 型`。

---

## 目標
- **9割は言語の中で自由に書ける。** React や Python で普通に作るアプリは、この言語だけで作れる。
- **残りの1割は action の中身に閉じ込める。** 契約（example・never・else）だけ書いて、中身はAIか自分が埋める。
- **if・for・true/false は入れない。** 入れた瞬間に普通の言語に戻るから。代わりに match・list・状態で書く。
- **書かなかった所はAIが決める。書いた所はその通りにしか作れない。** 画面の見た目も同じ。

---

# A. 画面

## A1. scene（場面）と移動
```
scene Home
  top     Header
  main    DueSoon as cards
  side    Application as list
  bottom  button 追加

flow scene
  Home -> Detail -> Edit
  Home -> AddApplication

rule OpenDetail
  when  user taps card on DueSoon
  do    go Detail with this
```
- scene は置き場所に何を置くかだけ。上から書いた順に並ぶ。
- 置き場所の名前: `top` `main` `side` `bottom` `over`（上に重ねる）。
- 細かく並べたい時は `row` `column` `grid 3` を置き場所の代わりに使える（A4）。
- 移動は flow scene の矢印の通りだけ。矢印に無い移動を rule で書いたらエラー。
- `this` は押された1件。`with this` で次の場面に渡す。

## A2. look（見せ方）
```
look DueSoon as cards
  title   company
  sub     deadline
  mark    color of status
  button  提出した
```
見せ方の種類:

| 種類 | 用途 |
|---|---|
| cards / list / table | 並べる |
| detail | 1件を詳しく |
| input | 入力（A5） |
| calendar | 日付で並べる |
| board | 状態ごとの列（flow から列が自動でできる。カードを動かすと move） |
| chart | グラフ（line / bar / pie） |
| tabs | 切り替え |
| dialog / sheet | 小窓、下から出る板 |
| toast | 一瞬出る通知 |
| map | 地図（connect が要る） |
| media | 画像・動画 |

## A3. part（自分で作る部品）
```
part DeadlineBadge
  in     deadline date
  show   text "あと {days until deadline} 日"
  mark   color of urgency

look DueSoon as cards
  title  company
  sub    DeadlineBadge of deadline
```
- 自分で見せ方を作って名前を付ける。どこでも使い回せる。
- part の中に part を使うのは可（名前で呼ぶだけなので入れ子ではない）。part の中に part を定義するのは不可。

## A4. style（見た目）
```
style DueSoon
  card     round 12, shadow soft, pad 16
  title    size 18, bold
  mark     dot left
  gap      16
  enter    fade 200ms
  reorder  slide 150ms

style Home on phone
  main     column
style Home on wide
  main     grid 3
```
- 色・大きさ・余白・角丸・影・フォント・動き・並べ方まで全部書ける。
- 書かなかった所はAIが決める（標準デザインを土台に）。
- `on phone | tablet | wide` で画面の大きさごとに変える。
- 共通の色や大きさは `style theme` に名前で置く（`color main #2F6FEB`、`space s 8`）。

## A5. input（入力）
```
input AddApplication
  company   required
  deadline  required, from now
  memo
```
- 送ったら `Application is created` の出来事が起きる。
- 入力のチェック（required、範囲、形）は項目の隣に書く。満たさない時の表示は言語が出す。

## A6. 画面だけの状態
```
scene Home
  menu[open | closed] = closed
  tab[soon | all | done] = soon

rule ToggleMenu
  when  user taps menu
  do    move menu to open

relate
  ...
```
- 画面の状態も `[ ]` の状態で持つ。true/false は無し。
- 変えるのは rule の move だけ。flow を書けば移り方も縛れる。書かなければ自由に移れる。

## A7. 出し分け
```
scene Home
  main  match count of DueSoon
          0    -> EmptyNote
          else -> DueSoon as cards
  menu-area match menu
          open   -> Menu
          closed -> nothing
```
- if は使わず match。状態を全部書けば else 不要（v0.2 の決まり）。
- `nothing` は「何も出さない」。

## A8. 細かい操作
when に書ける出来事に足す:
`user taps X` / `user holds X` / `user swipes X left` / `user drags X to Y` / `user types in X` / `user opens Scene` / `user leaves Scene`

## A9. 自由な絵
- 言語の見せ方で足りない絵（自作の図など）は `part 名前 by ai` にする。中身はAIが描く。
- 検証は example で「このデータの時、こうなっているか」を書く（例: `example given 3 items expect 3 bars`）。見た目の良し悪しまでは機械で検証できない。これは正直な限界。

## A10. 多言語と読み上げ
```
words ja
  add  追加
words en
  add  Add
```
- 画面の文字は words の名前で書ける（`button add`）。
- **決めてないことはエラー**を画面にも: 画像に説明文が無い、ボタンに名前が無い、words に片方の言語だけ訳が無い、はビルド前にエラー。

## A11. リアルタイム
- 何も書かなくても、画面は常に最新になる。箱（thing 1件）が変わったら、それを見せている画面が自動で変わる。
- 箱＝アクターの設計がそのまま効く。React では自分で書く部分を、言語が持つ。

**A の決めたいこと**
1. 置き場所の名前はこの5つ（top / main / side / bottom / over）でいいか
2. style の `on phone | tablet | wide` の3段階でいいか
3. 画面の状態を rule の move だけで変えるのは面倒すぎないか（`toggle menu` みたいな短縮を許すか）
4. 読み上げ対応をエラーにするのは厳しすぎないか

---

# B. ロジック

## B1. do の道具（標準で持つもの）
| 種類 | 道具 |
|---|---|
| 文字 | length, trim, lower, upper, normalize（全角半角）, split, join, replace, find all Shape, starts with, contains |
| 数 | sum, min, max, avg, round, abs |
| 日時 | weekday of, days until, add 3 days, date of, time of, start of day, end of day |
| 集まり | count of, first of, last of, each, sort by, group by, unique, take 3 |
| 形 | shape（正規表現の代わり。名前で部分を取り出す） |
| 読み書き | read json, write json, read csv, write csv |

- 名前は既存の言語でよく使う語に寄せる（AIが間違えにくい）。
- ループと再帰は無し。`each` と `sort by` は数に上限がある集まりにだけ使える。だから必ず止まる。
- これで足りない計算は action の by ai / by code に押し込む。

## B2. 数と単位
```
thing Plan
  price  money yen
  rate   percent
  seats  count
```
- `number` の他に `money`（通貨付き、小数の誤差なし）、`percent`、`count`（0以上の整数）。
- 通貨の違う money を足したらエラー。

## B3. 年なし日時と契約の矛盾（他のAIの指摘）
- 型 `monthday`（月日と時刻、年なし）を足す。
- ExtractDeadline は `out found monthday | missing` にする。
- チェッカーに **E13 契約の矛盾** を足す:
  - example の答えが out の型に合わない
  - never と out の型がぶつかる（`never guess the year` なのに out に年が要る）

## B4. by ai と ask ai（他のAIの指摘）
| 書き方 | いつAIが動くか | 中身 |
|---|---|---|
| `by ai` | ビルドの時に1回 | AIが do を書いて固定。人も読める |
| `ask ai` | 実行の度に毎回 | AIに聞く。do は無い |
| `by code "x.lang"` | — | 自分で書いた do |
| `by Gmail` | 実行の度に | connect 先がやる |

- どれも同じ example・never・else で検証する。
- ask ai は how に上限を書くのが必須（`limit 5 seconds`、`cost 1 yen`）。無いとエラー。

## B5. ファイルと画像
- 型 `file` `image` `pdf` を足す。
- input で受け取れる（`resume file, pdf only, max 5 MB`）。
- do の道具に `text of pdf`、`size of image` を足す。
- 保存は言語が持つ（C2）。

**B の決めたいこと**
1. 道具の一覧はこの範囲で始めていいか
2. money / percent / count を足すか
3. ask ai の上限を必須にするか

---

# C. データと人

## C1. 誰ができるか（who）
```
who
  user   can see    Application where owner is me
  user   can change Application where owner is me
  admin  can do     everything
  nobody can remove Application
```
- `me` は今使っている人（仕様の current user）。
- **書いてないことは誰もできない。** thing ごとに who が1行も無ければエラー（決めてないことはエラー）。
- rule も who に従う。「user says」で動く rule は、その人ができることしかできない。
- ログインの方法（パスワード・Google など）は connect に任せる。

## C2. データの保存
- 保存は言語が持つ。thing を書けばデータは残る。何のDBかは書かない。
- 自前の実行エンジンでは、1つのファイルに書き足していく形（ログ）から始める。依存ゼロで作れる。

## C3. thing を変えた時（今あるデータの扱い）
```
change Application to v2
  add     memo text = ""
  rename  company to corp
  remove  owner
```
- thing の形が前回のビルドと違うのに change が無ければエラー。
- 足した項目の初期値が無ければエラー（決めてないことはエラー）。
- 状態を消す時は、その状態だった箱をどこへ移すかを書くのが必須（`remove state passed -> failed`）。

## C4. 消した時の扱い
```
thing Application
  company  Company  gone[remove too | leave empty | block]
```
- 他の箱を指す項目には、指した先が消えた時どうするかを必ず書く。無ければエラー。
  - remove too：一緒に消す
  - leave empty：空にする（その項目は空を許す型になる）
  - block：指されている間は消せない

**C の決めたいこと**
1. who が無い thing をエラーにするか（厳しいけど一番安全）
2. change の書き方でいいか
3. gone の3択でいいか、語はどうか

---

# D. 外とつながる（connect）

```
connect Gmail
  gives   new message  Message
  does    send mail    to text, body text -> sent | failed
  needs   key GMAIL_TOKEN
  limit   100 per hour
```
- `gives`：向こうから届く出来事。rule の when で `when Gmail gives new message`。
- `does`：こちらから頼めること。結果は必ず状態（`sent | failed`）。
- `needs`：秘密の値。値そのものは仕様に書かず、実行する時に渡す。
- `limit`：回数の上限。
- 失敗した時の逃げ道は relate の else か、rule の中で結果を match して書く。どちらも無ければエラー。
- 依存ゼロとの関係: 言語の中は依存ゼロ。外との境界は connect に宣言した口だけ。

**D の決めたいこと**
1. gives / does / needs / limit の4語でいいか
2. `does` の結果を必ず状態にするのは厳しくないか

---

# E. テスト（example）

rule の example を、出来事ごとに書けるようにする。
```
rule MarkSubmitted
  when  user says "submitted {company}"
  do    move Application where company is {company} to submitted
  example
    given   Application(company "Osaka Gas", status draft)
    given   Application(company "Other", status draft)
    says    "submitted Osaka Gas"
    expect  Application(company "Osaka Gas") is submitted
    expect  Application(company "Other") is draft
```
- 出来事の行: `at "9/21 21:00"` / `says "..."` / `taps 提出した on ...` / `gets Gmail new message "..."`
- 結果の行: `expect notify "..."` / `expect X is 状態` / `expect scene Detail` / `expect nothing`
- 画面にも example を書ける（`expect Home shows 2 cards`）。

**E の決めたいこと**
1. given / 出来事 / expect の3段でいいか

---

# F. まとまりと共有

- group は v0.2 で決定。
- ファイル分け: `use "mail.lang"` で別ファイルの group を使う。
- 部品の共有（パッケージ）: 他の人が **この言語で** 書いた group を `use "名前" version 1.2` で持ってくる。中身の指紋（ハッシュ）で固定する。他の言語のライブラリは持ち込まない。
- パッケージは後回しでいい（最初は1人で作るから）。

---

# G. 作る道具

| 道具 | 中身 | 優先 |
|---|---|---|
| チェッカー | 決めてないことを全部止める。今あるものを v0.2 に合わせる | 最初 |
| 実行エンジン | 自前。spec を読んで動かす。ブラウザにも出す | 最初 |
| 見た目の即時表示 | 書き換えたらすぐ画面が変わる | 2番目 |
| エラーを spec の行に戻す | 実行中に壊れても「何行目」で分かる | 2番目 |
| AIに do を書かせるループ | 文法とチェッカーのエラーを返して、example が全部通るまで直させる | 2番目 |
| エディタの色分けと補完 | 仕様7章の色分け | 3番目 |
| 整形 | 誰が書いても同じ見た目 | 3番目 |
| WebAssembly への変換 | 速さのため | 最後 |

---

# 新しく足す語の一覧（この案を全部入れた場合）

| 種類 | 語 |
|---|---|
| 見出し | scene, look, part, style, input, who, change, connect, words |
| 画面の中 | top, main, side, bottom, over, row, column, grid, as, show, button, nothing, this, go, with |
| 画面の出来事 | taps, holds, swipes, drags, types, opens, leaves |
| 型 | monthday, money, percent, count, file, image, pdf |
| データ | can, me, everything, nobody, gone, add, rename, remove |
| 外 | gives, does, needs, limit |
| テスト | says, expect, shows |

語は増えるけど、どれも1つの仕事だけで、同じ意味の語は1つだけ。
