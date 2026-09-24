# 変更の記録

細かい作業の記録は [REPORT.md](REPORT.md)。ここは「何が入ったか」だけ。

## 上位レイヤーの言語へ（2026-09-24）

- 位置づけ: Ponte はプログラムのいちばん上の層に書く言語で、Python や Java はその下の層になる。AI は前提にせず、使うときの選択肢にする。README・仕様書0章・ホームページを書き直した
- action の中にその場で書いた `do` が動くようになった（AI も別ファイルも使わずに完結する）
- match の範囲 `60..` が、文字や小数で来た数にも当たるようになった
- エラーと出力が英語でも出る（`--lang en` / `PONTE_LANG` / システムの言語）。訳は `ponte/i18n_en.json`
- `ponte check` の出力を「止まります」「決めていないことはありません。動かせます」に
- エラーと出力は英語が標準に（日本語は `--lang ja` / `PONTE_LANG=ja`）
- 見出しを書いて Enter を押すと、必須の部品の名前だけが入る（「試す」と `ponte lsp`）。必須の部品の表は `ponte/skeleton.py` の1か所で、抜くと本当にエラーになることをテストで確かめる
- `rule` に `do` が、`action` に `in` / `out` がないとエラー（E28）になった
- `with` と `confirm`: 宣言した値が下の層で本当に効いたかを確かめる。下の層は実際に使った値を `report()`（`ponte/report.py`。ほかのプロジェクトにそのまま写せる）で報告し、Ponte が照合する。報告がない値も、違う値も止める。まずは `by python "x.py"` の action から（仕様 5章 with と confirm）
- `model`: レコードから学んで状態を当てる部品。書くのは learn（何を当てるか）・using（何を見てよいか）・require（合格の条件）・else（使えないとき）・example（必ず当てる例）で、学び方は書かない。`ponte train` で学び（NN は Python の標準機能だけで書いた ponte/nn.py）、`ponte test` が約束を確かめる。約束を満たさないモデルは使わず else に従う。`where predict Churn for it is yes` で使う（仕様 5章 model、見本 spec/churn.ponte）
- IR（中間の形）と共通テスト: `ponte ir` で check を通った仕様を JSON にし、`ponte conform` で共通テストを流す。IR から仕様に戻しても何も失わない。`ponte test` も同じ手順の形で動く（[docs/IR.md](docs/IR.md)）
- ホームページ: 固定の上のバー、スクロールしても見える目次、アニメーション、先頭へ戻るボタンなど

## 格上げ（2026-09-23）

### 言語
- **画像**: `photo image` の項目を input で選べる（種類は中身で確かめる・5MB まで・名前はランダム）。look の `image photo about name` で一覧に写真。who で見られる人にだけ出る。備品かしだしに写真
- chart に `group by 項目` と `sum 項目`（家計メモに「費目ごとの合計」）。input の状態の項目は選ぶ形に（flow のある状態は選べない）
- when に `every month on 1 at 9:00` / `every month on last at 18:00`（無い日の月は月末に）
- shape に `one of "a" "b"`（どれか1つ。名前も付けられる）と `edge`（数字・英字の続きの途中で始まらない・終わらない）
- 道具: `avg of` / `abs` / `date of` / `time of`。`round` を本当の四捨五入に（2.5 → 3。前は Python の round で 2）
- 標準ライブラリに `FindDate`（年の入った日付）と `FindPostal`（郵便番号）
- 状態は `status  [todo | done]` と、名前と [ の間を空けて書く（型の列にそろう）。`ponte fmt` もそう整える。詰めて書いても読める

### 動かす前に止める（チェッカー）
- **打ち間違いが黙って通らない**: 見本の行の言葉を1つずつ打ち間違えて流すテストで、黙って無視されていた所を全部塞いだ。条件の無い rule になる（`wher`）、一覧が黙って空になる（`where status is otdo`）、who の権利が黙って効かない（`cna`・`chnage`・`where woner`）、flow に黙って新しい状態ができる（`otdo -> done`）、画面を開くと止まる（input の項目）、ほか sort・example・expect・画面の置き物と見せ方・input の決まり・色・mark・ボタン・gives・create の値と期間・else・out の型
- **壊れた仕様で落ちない**: でたらめに壊した仕様を何万通りも流して、Python のエラーで落ちる所と「check は通るのに動かすと止まる」所を塞いだ（example の手順の打ち間違い `expekt` が黙って無視され、確かめていないのに通っていた、など）
- 「もしかして …？」（名前・状態・見出し・型・do・when・節）
- **エラーの辞書**: `ponte explain E32`（なぜ止めるか・どう直すか）。check のエラーの下に「直し方: ponte explain …」。仕様書 13章の表もここから作る

### 道具（コマンド）
- `ponte doc`: 決めごとを、コードを読まない人にも読める1枚の HTML に（データ・流れ・誰が何をできるか・きまりと理由・AIに任せた所・画面・残っていること）
- `ponte lsp`: 言語サーバー（Neovim・Helix などでもエラー・説明・補い）。VS Code は保存するとエラーの行に波線
- `ponte run --reload`（書き直すと読み直す。通らない書き直しは前のまま）・`ponte check --watch`
- `ponte check --json` / `ponte test --json`
- `ponte data export`（JSON / CSV）・`import`（CSV から。全部の行を先に確かめ、1行でもダメなら何も入れない）・`compact`（記録を今の中身1枚に。使われていない画像も消す）
- `ponte new myapp --from lend`（見本のアプリから始める）・`ponte --version`（0.3.1）

### 動かす（実行エンジンと画面）
- **本当のログイン**: `ponte run --login`（名前と合言葉。scrypt・HttpOnly の cookie・間違いが続くと少し止める）。`--signup` で画面から登録（同じところから1時間に5人まで）。`ponte user add / remove / list`（動かしている間でも効く。消した人はその場で切れる）。`--login` 無しで外に開こうとすると止める
- **守り**: 他の人の箱を id で開けた・押せたのを止めた／URL の `lang` から脚本を差し込めた穴／サーバーのエラー文を HTML として出さない／埋め込み禁止などのヘッダー／見ている人を要求ごとに持つ／宛先の無い通知は、管理者のいるアプリでは管理者だけに／変な形のリクエストにも JSON のエラー
- **見直しで塞いだ穴**（別の目で読み直してもらった）: 画面の登録で、いる人の合言葉を上書きできた／先に管理者にした名前を、あとから画面で登録して名乗れた／入力に無い項目（持ち主など）を送れた／別の thing の箱を this に指せた／深い JSON で要求が落ちた／保存できない時にも画像を残していた／よそのページからログイン・ログアウトさせられた／言語サーバーが変な1通で止まった
- **1つのファイル（.pyz）のデータが消えていた**: 動かすたびに一時フォルダに残していたので、動かし直すと空になっていた → .pyz の隣に残す（`PONTE_DATA_DIR` で変えられる）。`python app.pyz --port 8080` や `python app.pyz user add taro` も通るように
- **データを失いにくく**: 書くたびにディスクまで書き切る（fsync）。書きかけの最後の1行は捨てて起動、途中の行が壊れていたら黙って進まずに止める
- 画面を速く（2万件で 1.2 秒 → 0.6 秒）。押せるカードはキーボードでも（Enter / Space）、board のカードは ← → で隣の列へ

### ホームページ
- 「試す」: ブラウザの中で check と test が動く（本体をそのまま Pyodide で。インストール不要・書いたものは送らない）。「共有」で URL に入れて渡せる。「決めごと」で ponte doc
- 「入門」（コードごとに「このコードを試す」）・「道具とエラー」・「仕様書」・「しくみ」のページ。docs と実装から作り、ずれたらテストが落ちる
- README の英語版（README.en.md）

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
