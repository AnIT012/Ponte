# QUESTIONS v0.2 — チェッカーを作り直して出てきた、仕様に書いてない判定

仕様 v0.2 に書いてない細かい所は、下の「仮」で実装した。違っていたら直す。

### V1. action の else と relate の else（E04 と E17）
仕様では「action に else が無い → エラー」と「逃げ道が2つ → エラー」の両方がある。
そのままだと、action に relate の else を付ける方法が無くなる。
- 仮: action の else **か** relate の `A else B` の**どちらか1つ**があれば E04 は通る。両方あれば E17。

### V2. connect の does の失敗の逃げ道（E23）
仕様は「relate の else か、結果を match して書く」。rule の do は1行なので、結果を match する書き方がまだ無い。
- 仮: rule の do で connect の does を呼んだら、relate に `その rule else 〇〇` が必要。

### V3. どの画面からの移動か（E24）
rule には「どの画面にいる時か」を書く所が無い。
- 仮: when から推測する。`user taps X on L` なら L を表示している scene、`user opens S` なら S。
  推測できなければ「flow scene のどこかに移動先がある」だけを見る。
- input も1つの画面として数える（仕様の付録で `Home -> AddApplication` と input AddApplication が対になっているため）。
- flow scene は分かれ道があっても `>` を求めない（1人の操作なので同時には来ない）。

### V4. thing の形の保存（E21）
「前回のビルドと違う」を知るには前回の形が要る。
- 仮: `python -m lang check x.lang --save-shape` で、通った時に `x.lang.shape.json` に残す。次の check はそれと比べる。
  ファイルが無ければ初回として比べない。

### V5. 通貨の混ぜ（E27）
- 仮: 1つの行に `+` `-` `sum` があり、通貨の違う money の項目名が2つ以上出てきたらエラー。項目名だけで見ている（型の推論はしていない）。

### V6. 契約の矛盾（E13）で見ているもの
- 仮: (1) never に year があって out に date がある、(2) example の答えが out のどの状態名にも当たらない、(3) out が date なのに答えに4桁の年が無い。
- monthday なのに答えに年が付いている場合は見ていない。

### V7. before の左が「起きうる」か（E16）
- 仮: when を持つ rule、do の中で呼ばれる action、then / else でつながった先、を「起きうる」とする。
  存在しない名前も「起きえない」として E16 にした。
- relate の他の行（then / > / else）に存在しない名前がある場合は、エラー一覧に無いので止めていない。止めたい？

### V8. 読み上げ対応（E26）の対象
- 仮: scene / look / part の中の `button 名前` に `named` が無い、`image 名前` に `about` が無い。

### V9. 付録のタイムゾーン
付録は `tbd timezone of deadline` で止まる。`spec/hub_ready.lang` は tbd を外しただけ。答えが決まったら書き足す。

---

## R. 実行エンジンを作って出てきたこと

### R1. 時間や外からの出来事で動く rule は、誰の権限で動く？
- 仮: 人がきっかけでない rule（every day at / Gmail gives / データの変化の連鎖）は、who の制限を受けずに仕組みとして動く。
  人がきっかけの rule（user says / user taps）は、その人の who に従う。

### R2. input で作った箱の、User を指す項目
`input AddApplication` には company と deadline しか無い。owner は？
- 仮: User を指す項目は、作った人（me）を自動で入れる。状態の項目は flow の最初の状態（draft）。

### R3. 通知の宛先
`do notify each of DueSoon` は誰に届く？
- 仮: 人がきっかけならその人。時間で動いたなら、その箱の User を指す項目の人（owner）。

### R4. action の中身がまだ無い時
by ai の中身は、次の段階（AIに書かせるループ）で作る。
- 仮: 中身が無い action を呼んだら、そのまま else に進む（ask user なら「確認してください」と通知）。

### R5. example の年
example の日時（`"9/21 21:00"`）には年が無い。
- 仮: 年は推測せず、決まった年（2026）で読む。年をまたぐ example は書けない。

### R6. 画面の状態（toggle / set）はどこで持つ？
- 仮: ブラウザ側（見ている人ごと）。今回の実装では画面の状態を使う例がまだ無いので未実装。

### R7. 書かれていない部品（Header など）
仕様の付録の `top Header` は、Header がどこにも定義されていない。
- 仮: 定義が無い名前は、その名前を薄い文字で出すだけ。エラーにはしていない。エラーにするべき？（決めてないことはエラー、なら止めるべき）
