# 見直しメモ — ダメだと思ったパーツと、欲しいもの

**2026-09-23: おすすめ通りで進めることになり、下の「対応」の通りにした。残っているのは B2・B6・B8 と、C の connect does・map / media だけ。**

全体を洗練する中で気づいたもののうち、**言語の形が変わるので勝手に直さなかったもの**。判断してほしい。
すぐ直せる粗（道具・散らかり・仕様と実装のズレ）は直した。最後に一覧がある。

---

## A. ダメだと思ったパーツ

### A1. `given Application(company "Osaka Gas", status draft)` だけ書き方が違う
言語の中で、カッコと `,` を使うのはここだけ。他は全部「字下げ＋1行1つ」。
```
今:
  given   Application(company "Osaka Gas", deadline "9/24 23:59", status draft)
案:
  given Application
    company   "Osaka Gas"
    deadline  "9/24 23:59"
    status    draft
```
長くなるけど、入れ子禁止・1行1つの原則に揃う。AIも間違えにくい。**おすすめ: 案に揃える**。


→ **対応済み**: 字下げして1行1つ。古いカッコの書き方は E12 で止まる。
### A2. rule の `do` を2行書くと、順番が生まれる
`do` を2行書くと上から順に動く。「順序を書かない」原則に反してる。
**おすすめ: rule の do は1行だけにして、2つやりたい時は rule を分けて relate の `then` でつなぐ。** チェッカーで止める。


→ **対応済み**: do は1つだけ（E29）。
### A3. 通知の宛先が書いていない
`notify each of DueSoon` が誰に届くかは、言語が推測してる（その箱の User の項目）。「決めてないことはエラー」に反する。
```
案:  do  notify owner each of DueSoon
     do  notify me "保存しました"
```
**おすすめ: 宛先を必須にする**。


→ **対応済み**: `notify me` / `notify owner` と宛先を書く（E30）。
### A4. part の中の計算だけ、do と書き方が違う
action の中身は `do` の下に書くのに、part の中は `left = ...` をそのまま書いてる。
```
案:
part DeadlineBadge
  in    deadline monthday
  do
    left = days until deadline
    urgency[...] = match left
      ...
  show  text "{deadline} ・ {label}"
```
**おすすめ: part でも do の下に書く**。覚えることが1つ減る。


→ **対応済み**: part の計算も do の下。
### A5. `user does 〇〇` が自由すぎる
when は閉じたリストなのに、`user does` の後ろは何でも書ける。何が起きたら動くのか決まっていない。画面の出来事（taps など）ができた今は要らない。**おすすめ: 消す**。


→ **対応済み**: `user does` を消した。
### A6. 画面の文字の多言語が二重になる
`named 提出した` と書いて、words に `"提出した" Mark submitted` と書く。日本語を2回書くことになる。
```
案:  button submitted-button named submit        # words の名前で書く
     words ja   submit  提出した
     words en   submit  Mark submitted
```
**おすすめ: words がある spec では、画面の文字は words の名前で書く**（words が無い spec は今まで通り直接書ける）。


→ **対応済み**: words がある spec では画面の文字は words の名前（E25）。言語が出す文字も訳せる。
### A7. ボタンの強さ（tone）だけ、style の置き場所の決まりが違う
style は look や scene の名前で塊を作るのに、tone はボタンの名前でどこに書いても効く。
**おすすめ: tone は look の中のボタンの行に書く**（`button failed-button named 不合格 tone danger`）。


→ **対応済み**: tone はボタンの行に書く（style に書くと E28）。
### A8. `flow scene` が flow を2つの意味で使っている
状態の流れと、画面の移動。見た目は同じで分かりやすいけど、`>`（ぶつかった時）は画面には要らないなど、決まりが少し違う。今のままでもいいと思うけど、気になるなら `move scene` のように分ける手もある。**おすすめ: このまま**。


→ **このまま**。
---

## B. 欲しいもの

| # | 欲しいもの | 理由 | 大きさ |
|---|---|---|---|
| B1 | 並び順の向き `sort deadline desc` | 新しい順が書けない | **対応済み** |
| B2 | 年をまたぐ締切の決まり（**判断待ち**） | 12月に来年1月の締切を足すと、今の年として読んでしまう。tbd にさせるか、「今より前なら来年」と決めるか | 小 |
| B3 | 機械が確かめる never を増やす | `return empty` と `fail` を足して4つに | **対応済み** |
| B4 | エディタの色分け | `editor/vscode/`（依存なし） | **対応済み** |
| B5 | 1つのファイルに固めて渡す | `lang build` で `python app.pyz` | **対応済み** |
| B6 | 元に戻す（**判断待ち**） | flow は戻れないので、押し間違いを直せない。flow に戻る矢印を書くか、「直前の move だけ取り消せる」を言語で持つか | 中 |
| B7 | 一覧の件数が多い時 | `take 20` と「もっと見る」 | **対応済み** |
| B8 | WebAssembly への変換 | 仕様の最終形。速さと、どこでも動くこと | 大 |

---

## C. 仕様にあるのに、まだ動かないもの（正直な一覧）

| 仕様の場所 | 何が | 今 |
|---|---|---|
| 7.3 gone（**対応済み**: `do remove this` で消すと gone の通りになる） | 指した先が消えた時の remove too / leave empty / block | チェッカーは見るが、消す操作がまだ無いので動かない |
| 7.4 change（**対応済み**: 動かす時に古いデータを移す） | thing の形を変えた時にデータを移す | チェッカーは見るが、実行エンジンは古いデータを移さない |
| 5 how（**対応済み**: limit と retry が効く） | limit / on failure retry / until | 実行エンジンでは効いていない（v0.1 の Go 変換では効いていた） |
| 5 ask ai（**対応済み**: 答えが out の形でなければ else へ） | 実行の度にAIに聞く | チェッカーだけ。実行はまだ |
| 8 connect does | 外に頼む（メールを送る） | 形だけ。本当につなぐのは中身の仕事（相談で後回しに決めた） |
| 6 input（**対応済み**: required と from now を画面とサーバーで守る） | `from now`、`pdf only, max 5 MB` などの入力のチェック | required だけ効く |
| 6 look | map / media / table の細かい見せ方 | map と media は無い |
| F use（**対応済み**: 別ファイルを取り込む。エラーは元のファイルと行で出る） | 別ファイルの group を使う | まだ |

---

## D. 今回直したもの（勝手に直してよい範囲）

- **散らかり**: v0.1 の実装・Go 変換・旧実験を `archive/v01/` に。設計メモを `docs/design/` に。テストは今の言語だけ流す。
- **仕様と実装のズレ**: `expect Home shows 1 card` が読めなかった → 読める。`never depend on width` と答えの行の決まりを仕様書へ。道具の章を足した。
- **決めてないことはエラー**: どこにも無い型の名前（`owner Usr`）が素通りしていた → エラー28。
- **道具**: エラーを `ファイル:行` で出す（エディタで押せる）。整形 `lang fmt` を足した（コメントを消さない。意味が変わるなら書き換えない）。
- **仮の決めごと**: 2つのファイルに48個散らばっていたのを、`docs/DECISIONS.md` の1枚（26個、おすすめ付き）にまとめた。
