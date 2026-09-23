# 変更の記録

細かい作業の記録は [REPORT.md](REPORT.md)。ここは「何が入ったか」だけ。

## 格上げ（2026-09-23）

- **本当のログイン**: `ponte run --login`（名前と合言葉。scrypt・HttpOnly の cookie・間違いが続くと少し止める）。`--signup` で画面から登録。`ponte user add / remove / list`（動かしている間でも効く。消した人のログインはその場で切れる。add し直すと合言葉の変更）。`--signup` は同じところから1時間に5人まで。`--login` 無しで 127.0.0.1 以外に開こうとすると止める
- **見直しで塞いだ穴**（別の目で読み直してもらった）: 画面の登録で、いる人の合言葉を上書きできた（同時に送ると）／`ponte role` で先に管理者にした名前を、あとから画面で登録して名乗れた（そういう名前は `ponte user add` で）／入力に無い項目（持ち主など）を送れた／別の thing の箱を this に指せた／深い JSON で要求が落ちた／画像を、保存できない時にも残していた／よそのページからログイン・ログアウトさせられた（ログアウトは POST だけに）／見られない箱に「動かせません」と答えていた（「見つかりません」に）／言語サーバーが変な1通で止まった
- **守り（画面のサーバー）**: 他の人の箱を id で開けた（`?this=`）のを止めた。何の権利も無い箱のボタンは押せない。URL の `lang` から脚本を差し込めた穴を塞いだ。サーバーのエラー文を HTML として出さない。埋め込み禁止などのヘッダー。見ている人を要求ごとに持つ（並列の要求で入れ替わらない）
- **データを失いにくく**: 書くたびにディスクまで書き切る（fsync）。止まった時に書きかけになった最後の1行は捨てて起動し、途中の行が壊れていたら黙って進まずに止める
- **エラーの辞書**: `ponte explain E32`（なぜ止めるか・どう直すか）。check のエラーの下に「直し方: ponte explain …」。仕様書 13章の表もここから作る
- **打ち間違いが黙って通らない**: 見本の行の言葉を1つずつ打ち間違えて流すテストで見つけた穴を塞いだ。where の項目と状態（一覧が黙って空・rule が黙って起きない・who の権利が黙って効かない）、sort の項目、example の状態と expect の書き方、画面の置き物と見せ方の種類、input の決まり、色の名前、mark、when の moves to / ボタンの名前 / gives、move … where、create の値と期間、else、out の型。そのほか flow の状態（`otdo -> done` で黙って新しい状態ができ、始まりの状態まで変わっていた）・input の項目（画面を開くと止まっていた）・example の箱の中身の項目・who の行とできること・画面の置き場所・part と connect の節
- **節の打ち間違いを止める**: rule / list / action / look の中の知らない節（`wher status is todo` など）が黙って無視され、条件の無い rule として通っていた → E28 で止め、「もしかして where？」
- 打ち間違いらしい名前・見出し・型・do・when に「もしかして …？」
- 画面の API: 変な形のリクエストにも JSON のエラー（接続を切らない）
- 試す: 「共有」で書いたものを URL に入れて渡せる（# の後ろなのでサーバーには送られない）・「決めごと」で ponte doc
- ホームページに「試す」: ブラウザの中で check と test が動く（本体をそのまま Pyodide で。インストール不要・書いたものは送らない）
- ホームページに仕様書・しくみのページ（リポジトリが非公開でも読める）
- `ponte --version`（0.3.1）
- `ponte check --json`（エディタや AI のループ向け。直し方も入る）・`ponte test --json`
- `ponte data export`（JSON / CSV）・`ponte data import`（CSV から。全部の行を先に確かめ、1行でもダメなら何も入れない）・`ponte data compact`（追記の記録を今の中身1枚に。前のものは .bak）
- 画面: 押せるカードはキーボードでも（Tab で選んで Enter / Space）
- **画像**: `photo image` の項目を input で選べる（種類は中身で確かめる・5MB まで・名前はランダム）。look の `image photo about name` で一覧に写真。画像は who で見られる人にだけ出る。備品かしだしに写真
- chart に `group by 項目` と `sum 項目`（家計メモに「費目ごとの合計」）。input の状態の項目は選ぶ形に（flow のある状態は選べない）
- when に `every month on 1 at 9:00` / `every month on last at 18:00`（無い日の月は月末に）
- 道具 `time of`
- shape に `one of "a" "b"`（どれか1つ。名前も付けられる）と `edge`（数字・英字の続きの途中で始まらない・終わらない）
- 標準ライブラリに `FindDate`（年の入った日付）と `FindPostal`（郵便番号）
- `ponte run --reload`: spec を書き直すと読み直して、開いている画面も読み直す。check が通らない書き直しは前のまま動かし続ける
- `ponte doc`: 決めごとを、コードを読まない人にも読める1枚の HTML に（書いた人以外が確かめるため）
- `ponte lsp`: 言語サーバー（Neovim・Helix などでもエラー・E32 の説明・名前の補い）
- VS Code: 保存するとエラーの行に波線（`editor/vscode/extension.js`。依存なし）
- ホームページに「入門」と「道具とエラー」のページ（docs と実装から作る。ずれたらテストが落ちる）
- 道具: `avg of` / `abs` / `date of`（年月日の当たりを "2026/10/15" に）
- **壊れた仕様で落ちない**: でたらめに壊した仕様を何万通りも流して、Python のエラーで落ちる所と「check は通るのに動かすと止まる」所を塞いだ（`tests/test_fuzz_checker.py` に残した）。見つかったもの: example の手順の打ち間違い（`expekt`）が黙って無視され、確かめていないのに通っていた / 読めない期間（`within 3 dys`）/ 空の sort / 矢印の片側が空の flow / 無い list への `each of` / 読めない日時の example / `name` の無い User / check の途中で読めない行があると check そのものが落ちていた
- `round` を本当の四捨五入に（2.5 → 3。前は Python の round で 2 になっていた）

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
