# 変更の記録

細かい作業の記録は [REPORT.md](REPORT.md)。ここは「何が入ったか」だけ。

## 洗練（2026-09-23）

- shape の中で別の shape を名前で使える（`maybe Clock`）。自分に戻る使い方はエラー
- 日付の道具 `add 3 days to X` / `weekday of X`（年の入った日付だけ。年は推測しない）
- 1つの言語だけのアプリなら words 無しで、画面の文字を `"文字"` でそのまま書ける

## 名前: Ponte（2026-09-23）

言語の名前を **Ponte（ポンテ）** に決めた。イタリア語で「橋」。人とAIの間、上の決まりと裏の Python の間にかかる橋。
- 拡張子 `.lang` → `.ponte`、パッケージ `lang/` → `ponte/`、コマンド `python -m ponte`（`pip install -e .` で `ponte` だけでも）
- エディタの色分けも Ponte に
- 実験の記録（experiment/v2/runs*・prompts）と archive は、当時のまま `.lang` で残した
- ホームページ（`site/`）と、GitHub Pages に出す仕組み
- `ponte new`: ひな形から新しいアプリを作る

## v0.3（2026-09-23）

仕様書を [v0.3](docs/言語仕様_v0.3.md) にまとめ直した（v0.2 と追補を1つに。決まりは同じ）。

### 言語
- **型（E32）**: rule ごとに this が何の thing かを推論し、無い状態・無い項目・値の型違い・this が決まらない rule を動かす前に止める。
- **do の書き方の検査（E31）**: 動かす前に分かるように。
- rule の `where`（押された1件の条件。合わなければ静かに起きない・ボタンも押せない）
- `create` の中身（字下げして「項目 値」）、`set 項目 to 値`、`move 項目 of this to 状態`、`action with 項目`、`result`
- 値: `this` / `me` / `"文字"` / `7 days from now`（年まで入れて保存）/ `{名前}` / `項目 of this` / `result`
- 役割: `thing User` の `role[member | admin]`。`where it is not me`。最初の管理者は `lang role`
- 画面の `stats`（件数と合計）、数の3けた区切り
- 標準ライブラリ `use std/date` / `std/money` / `std/contact`（中身もこの言語、example 付き）
- 道具: `contains` / `starts with`（答えは yes・no）/ `sort` / `take` / `unique` / `sum` / `min` / `max` / `round` / `名前 of X` / `text of X`
- shape の `word with "._-" 1..64`（英数字と記号だけ）
- `+` と `-` は一番弱くつなぐ。状態の名前と行の名前の重なりはエラー
- まだ実行エンジンが起こさない when（holds / swipes / drags / types in / opens / leaves）は check で止める

### 道具
- `lang test` の**穴さがし**（example で確かめていない rule・flow の矢印・答えの形）。`--strict`
- example の `adds 箱` / `expect 箱`（中身）/ `expect no 箱` / `expect 2 箱`、別の箱を名前で指す
- `lang guide`: AIへの書き方の説明を**実装から作る**（道具・rule の書き方・never）。仕様書 10章の表も
- 他の言語のクセ（if / for / return / == / 正規表現）で書いたら、この言語での書き方を返す
- `lang role`、`lang build` に std を入れる

### 直したバグ
- 取り消しを押すと、他の箱も動いた時に半分だけ戻って食い違った → 押した1件だけが動いた時だけ出す
- 保存した直後に画面が入力に戻ってしまうことがあった（描画の追い越し）
- 無い画面の `shows` が0件として通っていた
- 仕様書の道具の表に、実装に無い道具（sum・weekday of・each など）が載っていた

### 見本・実験・リポジトリ
- 見本のアプリ: やること（入門）・備品かしだし・家計メモ
- 比較実験の3回目（Haiku・各6回）。エンジンをでたらめに叩くテスト
- README・[入門](docs/入門.md)・[仕組み](docs/仕組み.md)・[CONTRIBUTING](CONTRIBUTING.md)・GitHub Actions

## v0.2（2026-09-22）

「人が要件を書き、AIが中身を埋め、言語が守る」言語として作り直した。
- thing / flow / list / match / rule / relate / action / who / group / tbd / `##`
- 画面: scene / look / part / input / style / words（日本語と英語）、ボード・カレンダー・グラフ・ダークモード・スマホ
- 実行エンジン（箱ごとに鍵、箱をまたぐと並列、JSONL 保存）、画面のサーバー（SSE）
- action の中身を AI に書かせるループ（example と never で確かめて、問題を返す）
- 整形（`lang fmt`）、1ファイル化（`lang build`）、エディタの色分け
- 比較実験 v2（日本語で頼む vs この言語で頼む）
- 締切が今日より前なら「来年ですか？」と聞く。自分の直前の移動だけ取り消せる

## v0.1（2026-09-22）

最初の版。パーサとチェッカー、Go への変換、比較実験。今は [archive/v01/](archive/v01/) に当時のまま。
