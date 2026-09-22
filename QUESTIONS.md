# QUESTIONS — 仕様を読んで分からない点・矛盾している点

★は確定、△は提案。ここに書いたものは**勝手に決めていない**。
実装を進めるために「仮の扱い」を置いたものは *仮* と明記した。仮の扱いが違ったら直す。

## A. 就活Hubの例そのものについて

### Q1. `unknown` が残った例は、そのままだと「渡せません」になる
仕様のサンプルには `unknown` に `timezone of deadline` / `who can delete Application` が残っている。
「例をそのまま `.spec` にする」と、`spec/hub.spec` は仕様どおり**エラーで止まる**（これは言語の狙いどおり）。
- 仮: `spec/hub.spec` は原文どおり（止まる）。フェーズ2以降で使うため `spec/hub_ready.spec` を別に置き、`unknown` と `proposed` 行を外した。
- 質問: `timezone of deadline` と `who can delete Application` の答えは？（答えが決まったら hub_ready.spec に反映する）

### Q2. `ParseApplicationMail`（`use` による組み合わせ △）は example も else も無い
エラー一覧の「action に example が2つ未満」「action に else が無い」にそのまま当たる。
- 質問: `use` で組み立てた action は example / else 免除？ それとも必須？
- 仮: 免除しない（例外を作らない）。hub.spec ではエラーになる。hub_ready.spec には入れていない。

### Q3. `Message` 型が定義されていない
`action ExtractDeadline` の `input mail: Message` の `Message` は `connect gmail`（△）からしか出てこない。
しかも example は `"10/15(木)12:00まで" -> 10/15 12:00` と**文字列**を入力にしている。
- 質問: `Message` は text 扱いでよい？ connect の設計待ち？
- 仮: Go変換では未定義の型名を `type Message string` として出す（example を文字列として流せるように）。

### Q4. `ref User` / `ref Company` の先の entity がサンプルに無い
エラー一覧に「ref 先が未定義」は無い。
- 質問: 未定義の ref はエラー？ 警告？ 何もしない？
- 仮: 何もしない（エラー一覧に無いものは足さない）。Go変換では `UserID string` のようにIDだけ持たせる。

### Q5. `9/24 23:59` のように年もタイムゾーンも無い日時
Q1 の unknown と同根。example の期待値 `10/15 12:00` をどう比較するか決まっていない。
- 仮: フェーズ2の生成テストでは**文字列として一致**を見る（年の推測はしない = `never guess the year` に従う）。

### Q6. `match Application.status to color` の `color` は型？
`color` はどこにも宣言されていない。
- 仮: 結果は text として扱う。

## B. エラー一覧12個の「判定の定義」が仕様に無いもの

### Q7. 「flow の状態にルールの抜けがある（警告）」は渡せる？渡せない？
警告と書いてあるので、**渡せる**（件数には入れず「注意」として別表示）と仮に扱った。
判定の仮定義: ある flow の状態を `when 〇〇 moves to 状態` で1つでも使っていて、
初期状態以外の状態に使っていないものがあれば「passed のときは？」と出す。

### Q8. 「矛盾する move が同時に来うる」の判定
ルールは全部並列なので、言語側からは「同時に来ない」ことを証明できない。
- 仮: flow に分岐（`a -> b | c`）があれば、その `b`/`c` の組ごとに `on conflict` が必須。
- 質問: 「実際に b と c へ move するルールが両方あるときだけ」に絞るべき？

### Q9. 「入れ子」の判定
仕様の言葉は「条件の中に条件を書かない」「do の下に where は入れ子」。
- 仮の定義（この3つを入れ子エラーにした）:
  1. `do` の下の行（子）に `where` がある
  2. `where` の条件に `and` / `or` / `(` が入っている
  3. 子を持てない節（`from` `where` `when` `do` `because` `input` `output` `never` `else` `by` `use` `sort by`）の下にさらに行がある
- 矛盾に見える点: `do move Application where company is {company} to submitted` は do の**同じ行**に where がある。これは入れ子ではない（絞り込み）と解釈した。合ってる？

### Q10. 「move の対象が絞れていない」と、データ起点のルール
`when Application is created` → `do move Application to submitted` のように、出来事の対象が明らかな箱でも `where` は必須？
- 仮: 必須（例外を作らない）。

### Q11. 「when に状態を書いている」の判定
when は閉じたリストなので、リストに無い書き方は全部「状態」としてエラーにした。
`user does 〇〇` の 〇〇 は自由文として何でも受けている。合ってる？

### Q12. 「until に上限が無い」の判定
上限として受け付けた形: `N times` / `<期間> passed`（例 `1 hour passed`）。
- 質問: `check every 10 minutes` のように until の無い繰り返しは上限なし扱い？（仮: 何もしない）

### Q13. `proposed` の承認はどう書く？
`# proposed by ai` が付いた行は止める、までは仕様にある。**承認の書き方が無い**。
- 仮: マーカーを消せば承認。フェーズ4で `python -m lang proposals` に一覧させる。
- 質問: `# approved by <人>` のような明示の形が要る？

### Q14. `derive 〇〇 from 〇〇 using ai` はどこに書ける？
省略形とだけある。entity の項目？ list の where？ 独立した宣言？
- 仮: 宣言と同じ位置（行頭）と、entity / list の子として書ける。どちらも example 2つ＋else 必須で検査する。

### Q15. `never`（ファイル全体）の「証明できる違反」とは何か
エラー一覧の12個には無い。何を証明できるとするのかが無いので、**パースだけ**して検査はしていない。

## C. その他

### Q16. `because` は必須？（仕様の未決そのまま）
- 仮: 任意。無くてもエラーにも警告にもしない。

### Q17. `sort by` の向き
- 仮: 昇順。

### Q18. Python のバージョン
指示は 3.12 だが、この環境は 3.11 だった。3.12 だけの機能は使っていないので両方で動く。
