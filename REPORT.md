# REPORT — フェーズごとの報告

## フェーズ1：パーサーとチェッカー（完了）

### やったこと
- `spec/hub.spec`: 仕様書のサンプルをそのまま並べたもの。仕様どおり**渡せません（5件）**で止まる
  （unknown 2件、proposed 1件、`use` で組んだ action の example / else 無し 2件）。
- `spec/hub_ready.spec`: 上から unknown / proposed / ParseApplicationMail（△）を外した渡せる版。
  仕様本文にあった `when user says "submitted {company}" → do move ...` を rule MarkSubmitted として入れた。
- `lang/parser.py`: 行頭＝宣言、字下げ＝節の木。全ノードが行番号を持つ。タブ・字下げ不揃い・宣言以外の行頭はその行番号でエラー。
- `lang/checker.py`: エラー一覧12個を1つ1関数（`check_match_otherwise` … `check_nesting`）。
  「flow の抜け」は仕様どおり警告（W09）で、渡せる判定には数えない。
- `python -m lang check <spec>`: 「渡せません（N件）」＋箇条書き／「決めてないことなし。AIに渡せます」。警告は「注意（N件）」で別表示。終了コードはエラーあり=1。
- `tests/cases/`: エラーごとに broken.spec / fixed.spec のペア13組（入れ子は2種類）。broken は必ずそのコードで止まり、fixed はエラー0で通る。33テスト全部通過。

### 仕様に無くて仮で決めたこと（QUESTIONS.md に全部書いた）
- 入れ子の判定3つ（Q9）、on conflict 必須の条件＝分岐があれば必須（Q8）、when の閉じたリストの正規表現（Q11）、until の上限の形（Q12）、flow 抜けの判定（Q7）。
- `use` で組んだ action にも example / else を要求する（Q2）。

### 気づいたこと
- 仕様書のサンプル自体が「渡せません」になるのは、この言語の狙いを一番よく示している。実験（フェーズ3）でも hub.spec ではなく hub_ready.spec を使う必要がある。
- 環境の Python は 3.11（指示は 3.12）。3.12 専用の機能は使っていない。

## フェーズ2：決まった部分の Go 変換（完了）

### やったこと
- `python -m lang gen spec/hub_ready.spec -o generated/hub` で Go パッケージを出す。check を通らない仕様は変換しない。
- 変換の対応:
  | 仕様 | Go |
  |---|---|
  | entity | struct ＋ `XxxBox`（goroutine 1つ＋受信 channel。`Update` は届いた順に1つずつ）＋ `Store`（箱の集まり。`EachXxxParallel` で箱をまたぐ処理は並列） |
  | flow | 遷移表 `map[string][]string` ＋ `MoveStatus`（-> の通りにしか動けない）＋ `WinsOver` 表で on conflict |
  | list | `DueSoon(all, now)` フィルタ関数。where は and、list から list は関数呼び出し、sort by は昇順 |
  | match | `switch` ＋ `default`（otherwise） |
  | rule | 時間 → `Schedule` 値＋ `RuleRemind(store, effects, now)`。user says → 正規表現で `{company}` を取り出す `MatchMarkSubmitted` ＋ `RuleMarkSubmitted(..., company)`。move は箱ごとに並列 |
  | action | interface ＋ `XxxImpl` 変数（中身は空）＋ `RunXxx`（how の limit / retry を守る）＋ example からテーブルテスト（中身が無ければ skip） |
  | rule の example | `given` / `at` / `expect notify` からテスト |
- `generated/hub/` に変換結果をコミット（テストで最新か確認する）。`tests/go/semantics_test.go` は手書きで、生成物に対して flow / on conflict / 箱の直列化 / list / match / move の絞り込みを検証。`go test -race` 通過。
- 決定性: 同じ仕様を2回変換して完全一致をテスト。出力は spec の内容だけで決まり、辞書順・時刻に依存しない。gofmt があれば通す。
- 変換できない書き方（`where x seems related` など）は推測せず `CodegenError` で止まる。テストあり。

### 仕様に無くて仮で決めたこと
- **`within 3 days` は暦日**（QUESTIONS Q19）。72時間だと仕様書の example 自体が落ちる。変換して初めて分かった矛盾。
- on conflict の動き: 同じ分岐点から矛盾する move が続けて届いたら、勝者なら上書き、敗者なら何もしない（エラーにしない）。
- `Message` など未定義の型は `type Message string`（Q3）。`ref X` は `string` の ID（Q4）。
- 日時は年を推測せず、年 0 のまま比べる（Q5）。
- `user says` ルールの example の書き方が仕様に無いので、そのルールの example は変換できない（エラーで止まる）。

### 気づいたこと
- `connect`（△）からの出来事（`mail sends new message`）は変換できないので、フェーズ3の題材「メール→締切→通知」のうち「メール→」の入口は action の契約（ExtractDeadline）までしか言語で書けていない。

## フェーズ3：検証実験（基盤は完了、本番は API キー待ち）

### やったこと
- 同じ要件を2通りで用意: `experiment/prompts/A_japanese.md`（日本語の自然文）と `experiment/prompts/B_lang.md`（`spec/hub_ready.spec` そのまま＋読み方の8行）。
  両方に `experiment/prompts/common.md`（テストの窓口となる Go の型・関数と「分からなければコードを書かず `Q:` で質問だけ返す」）を付ける。
- 採点は `experiment/harness_test.go`（AI に見せない10テスト）。仕様の example 2つ、flow、on conflict、絞り込み、match、else、直列化（`-race`）。
- `experiment/run.py`: 各条件5回。モデルと effort を固定（Opus 5 系には temperature が無いので effort で代用）。ストリーミングで受け、```go ブロックを `hub.go` に切り出す。
- `experiment/score.py`: 動いたか／example 通過／バグ数（落ちたテスト数）／聞き返し（`Q:` 行の数）／5回のブレ（run 同士の差分行数の平均）を数えて `EXPERIMENT.md` を書く。
- **API キーが無いので `--dummy` でダミー結果を置き、手順だけ通した。** `EXPERIMENT.md` は「未実行」と明記した表。
- 検算: `experiment/reference/hub.go`（自分で書いた参照実装）がハーネス10テスト全部を通ること、わざと壊すと該当テストだけ落ちることをテストで保証。

### 本番のやり方
```
export ANTHROPIC_API_KEY=...
python experiment/run.py            # --model / --effort / --runs で固定値を変えられる
python experiment/score.py          # EXPERIMENT.md を上書き
```

### 正直に
- (B) は example / never / else / how が明示されている分、情報量で有利。(A) は慣れた自然文で有利。EXPERIMENT.md の注記に書いた。
- 「聞き返し」は機械的に数えるため、コードと質問を両方出した run は 0 と数える。

## フェーズ4：余力分（完了）

- **by code / by connect の骨組み**: `by code "file.go"` は「そのファイルの `init()` で `XxxImpl` を設定する」というコメント付きの置き場。`by connect gmail` は `connects.go` に `GmailEvents`（`sends` の出来事）と `GmailConnector`（by connect の action の中身）の interface を出し、`XxxByGmail` でつなぐ。connect が無いのに by connect したらエラー。
- **proposed の承認待ち**: `python -m lang proposals <spec>` が `# proposed` 行を一覧し、あれば終了コード1。承認は「マーカーを消す」（仕様に無いので Q13 で確認待ち）。
- **NAMES.md**: 候補10個。Web 検索で被りを調べ、おすすめは Sadame / Tsumori / Hitoai。商標DBは未確認。

## 全体の状態
- テスト48件通過（parser / checker 13ペア / codegen 決定性・go test -race / experiment 検算 / proposals）。
- **GitHub リポジトリは未作成**（このセッションの GitHub App に作成権限が無く 403）。ローカルの git にコミット済み。空リポジトリを作ってもらえれば push できる。
- 本番の実験は API キー待ち。

## v0.2：チェッカーの作り直し（完了）

- `lang/` を仕様 v0.2 で書き直した。v0.1 の実装は `lang_v01/` に退避（テストもそのまま通る）。
- パーサー: 見出し／節の木、`#` と `##` の2種類のコメント、`[a | b]` の状態、group の中の見出し。
- チェッカー: 13章のエラー27個を1つ1関数。警告は W09（flow の抜け）と W26（読み上げ対応、試作中）。
- `spec/hub.lang` は仕様書の付録そのまま。**tbd だけで止まる**（狙いどおり）。`spec/hub_ready.lang` は公開の検査まで通る。
- `tests/cases/` に壊した／直したペア34組。壊した方はそのコードだけで止まることも確認した。テストは v0.1 分と合わせて全部通る。
- 仕様に無い判定は `QUESTIONS_v0.2.md` に9件。特に V1（action の else と relate の else の関係）は仕様の矛盾に近い。

## v0.2：実行エンジン（最初のゴール達成）

**spec だけで就活Hubがブラウザで動く。** 依存は Python の標準機能だけ（Go も外部ライブラリも無し）。

- `lang/runtime.py`: 箱ごとのロック（同じ箱は1つずつ、箱をまたぐ rule は並列）、flow と `>`、list（within は暦日）、match、rule（時間・発言・タップ・データの変化・外から届いたもの）、relate（then / then no / before / > / else）、who、データの保存（1ファイルに書き足すログ、起動時に読み直す）。
- `lang/examples.py` と `python -m lang test`: rule の example（given / 出来事 / expect）を実行エンジンで流す。付録と hub_app の example は全部通る。
- `lang/server.py` と `python -m lang run`: scene / look / part / input / style を読んで画面を出す。箱が変わると開いている画面が自動で変わる（Server-Sent Events）。時間の出来事は1分ごとに見る。
- 実際にブラウザ（Chromium）で操作して確認した: 応募を3件足す → 20日後のものは「締切が近い」に出ない → 提出した → 通過 → 不合格で failed（`failed > passed`）→ スマホ幅で1列。
- テスト: 実行エンジンと画面で11件追加。全体で135件通過。

**まだ無いもの**
- action の中身（by ai）をAIに書かせるループ。今は中身が無ければ else に進む。
- do の中身の実行（shape、`名前 = 式`）。
- 画面の状態（toggle / set）、calendar / board / chart などの見せ方、画面の移動のアニメーション。
- 仮で決めた動きは `QUESTIONS_v0.2.md` の R 節に7件。

## v0.2：AIに中身を書かせるループ（完了、本物のAPIはキー待ち）

「人は決めて、AIが書いて、言語が守る」が一周した。

- `lang/body.py`: action の do と shape を動かす。if・for・ループ無しで、名前の依存で順番を決める。仕様書の ExtractDeadline の do がそのまま動き、example 4つと全角の入力を通る。
- `lang/fill.py` と `python -m lang fill`: 契約をAIに渡す → do を書かせる → 読めるか・チェッカー・example・never を機械で確かめる → ダメなら問題をそのまま返して書き直させる（既定5回まで）→ 通ったら `<spec>.ai/<action>.lang` に残す。
- 実行エンジンは残した中身を読んで使う。missing なら else（ask user）に進む。`python -m lang test` は action の example も流す（hub_app で9件全部通過）。
- **API キーが無いので、AIの役はこのセッションの Claude が引き受けた**（`experiment/ai_replies/`）。ループが送るのと同じプロンプトを読んで返事を書き、機械の確認は1回目で通った。
- テスト: 決まった返事を順に返すAIで、構文の間違い → 入れ子 → 答えの間違い → 正解、と4回目で通ること、各回の問題が次のプロンプトに入ることを確かめた。人が中身を書き換えて壊したら `lang test` が止めることも確かめた。
- E28（定義されていない名前）を足した。仕様書の付録にも Header / EmptyNote を足した。テストは全体で147件通過。

## v0.2：画面の作り込み（完了）

「書ける画面がしゃばい」を直した。就活Hub を、そのまま人に見せられる見た目にした。

- **見せ方**: cards / list / table に加えて、board（状態ごとの列、ドラッグで move）、calendar（月の表、前後の月へ）、chart（状態ごとの数）、detail（1件を詳しく）、dialog / sheet（小窓）、tabs。
- **画面の状態**: `tab[...]` `menu[...]` を toggle / set で切り替え。rule は要らない。
- **part**: 部品の中で計算できる（`days until`、match）。締切の札が「今日が締切」「あと2日」「締切を過ぎました」と色つきで出る。
- **標準のデザイン**: 色の変数、ダークモード、状態の札、ボタンの強さ（main / quiet / good / danger）、空の時の表示、読み込み中、通知、出てくる時と並び替えの動き、スマホで1列。
- **言語が画面を守る**: flow で動けないボタンは自動で押せない。board で flow に無い流れへ動かすと、人の言葉で断る。
- **words**: `?lang=en` で英語。words に書いた語が全部切り替わる。
- 見つけて直した言語のバグ: `#4F46E5` がコメントとして消えていた。`days until` が until の上限チェックに引っかかっていた。
- ブラウザ（Chromium）で、タブ・ボードのドラッグ（正しい流れと、断られる流れ）・詳しく・追加・メニュー・英語・スマホ・ダークを実際に操作して確かめた。テストは全体で152件通過。
- 足した語は仕様書 6章の「画面のための追補（要確認）」と QUESTIONS_v0.2.md の U 節。

## v0.2：言語で書ける画面を増やす（完了）

見た目だけでなく、spec に書ける画面の語を増やした。全部チェッカーが見る。

- アイコン（組み込み24個、`icon` と `match ... to icon`）、頭文字の丸（`lead`）、見出し（`heading`）、検索（`search`）、状態ごとのまとまり（`group by`）、空の時のボタン、押す前の確認（`confirm`）、お知らせのベル（`notices`）、編集（input を `with this` で開く）、引用符の鍵で spec の日本語もそのまま訳す（英語で画面の文字が全部切り替わる）。
- チェッカー: 無いアイコン名、look に書いた無い項目名、読めないボタンの行はエラー（28）。
- 見つけて直したバグ: 色の match と icon の match を両方書くと色が消えていた。メニューの小窓の背景がヘッダーの下に潜っていた。ボタンの名前に打ち間違いが紛れ込んでいた（名前は1語、空白は引用符に）。
- ブラウザで、検索・確認（やめる）・編集して保存・ベル・英語・スマホ・ダークを操作して確かめた。画面のエラー0件。テストは全体で163件通過。

## 比較実験 v2（完了）

「自然文で頼むより、この言語で渡す方がAIが間違えないか」を、今の形（この言語はAIが中身だけ書く）で測った。AIは Claude のサブエージェント（Sonnet）、各5回、同じ14個の隠しテスト。

| | (A) 日本語 | (B) この言語（1回目） | (B) ループ後 |
|---|---|---|---|
| 14テスト全部通った | 0/5 | 3/5 | 4/5 |
| 仕様の例を全部通った | 0/5 | 4/5 | 5/5 |
| バグ数の平均 | 2.2 | 0.6 | 0.2 |
| 推測で埋めた所（Q:） | 37 | 0 | — |

- (A) は5回とも「3日以内」を72時間と読み、要件に書いた例を自分で破った。
- (B) は1回、書き方の間違いがあったが、言語のループで直った。例に無い全角の数字は1回落ちたまま（言語は例と never に書いたことしか守れない）。
- 比べ方の偏りと限界は EXPERIMENT.md に全部書いた。

## 実験で見えた粗の修正と、2回目の実験（完了）

- 直した粗: 答えの行に out の形を書いてもよい / `never depend on width` を機械で確かめる / 書き方の説明 / lang test で never も流す / 返事の形のゆれ（契約まで書き写した返事）も読める。
- 2回目は日本語の要件にも「3日以内の数え方」と「全角」を同じだけはっきり書いた。
- 結果（実験した時の道具で）: (A) 全部通った 3/5・バグ平均1.0、(B) ループ後 5/5・バグ0。1回目の差の多くは曖昧さだったが、はっきりさせた後もこの言語の方が間違えなかった。(A) は1回あたり約7個の推測を書き、(B) は0。
- 弱い所も残る: 初見の書き方で1回ずつ失敗した（ループで直った）。例と never に書いてないことは守れない。

## 全体の洗練（完了）

- 散らかりの整理（v0.1 を archive へ、設計メモを docs/design へ）、仕様と実装のズレの修正、無い型の名前もエラー28に、エラーを `ファイル:行` で出す、整形 `lang fmt`、example で「画面に N 件」を確かめる。
- 仮の決めごとを `docs/DECISIONS.md` の1枚にまとめた（26個、おすすめ付き）。
- 言語の形が変わるので直さなかったもの（ダメなパーツ8つ・欲しいもの8つ・まだ動かないもの8つ）は `REVIEW.md`。

## DECISIONS と REVIEW をおすすめ通りに（完了）

- DECISIONS の26個を仕様書 11.5 章に★として書き写した。
- ダメなパーツ: example の箱は字下げして1行1つ / rule の do は1つ（E29）/ 通知の宛先（E30）/ part の計算も do の下 / user does を消す / words がある spec は画面の文字を words の名前で / tone はボタンの行に。
- 欲しいもの: sort の desc / never を4つに / take と「もっと見る」/ エディタの色分け / `lang build` で1つのファイルに。
- まだ動かなかったもの: 消す（gone の通り）/ change で古いデータを移す / how の limit と retry / ask ai / input の決まりをサーバーでも / use で別ファイル。
- 残り（判断待ち）: 年をまたぐ締切（B2）、元に戻す（B6）。大きいもの: WebAssembly（B8）。
- テスト155件通過。ブラウザで消す→確認→ホームへ戻るまで確かめた。

## 弱いところを埋める（完了）

「この言語どう？」で挙げた弱いところ4つに、それぞれ手を入れた。

1. **保証できる範囲が狭い → 穴さがし。** `lang test` が「どの example も確かめていない所」を出す（when があるのに確かめていない rule / 通っていない flow の矢印 / 出していない action の答えの形）。`--strict` で失敗にする。例が途中で止まった時は理由も出す。
2. **エンジン頼み → エンジンをでたらめに叩くテスト。** 40通り×60操作で、flow・who・通知先・ログの読み直しの約束が破れないことを確かめた（移動136回・削除141回などが実際に起きている）。
3. **1つのアプリでしか試していない → 2つ目のアプリ（`spec/lend.lang` 備品かしだし）。** 素直に書いてみて、足りなかった物を足した:
   - E31: do の書き方を check の段階で確かめる（今までは動かすまで分からなかった）
   - create の下に「項目 値」（`7 days from now` は年まで入れて保存）/ `move item of this to lent` / 通知の `{item}` は指している箱の名前
   - rule の `where`（貸し出し中の物をもう1回借りると2重になるバグを、書いて止められるように。ボタンも押せなくなる）
   - example: 名前で別の箱を指す / `expect no Loan` / 無い画面の `shows` は失敗に（今までは0件として通っていた）
   - 取り消しは、押した1件だけが動いた時だけ出す（借りる＝作る＋動かすを半分だけ戻すと食い違う）
   - 通知は2つまで・左下に
   - ブラウザで、足す→借りる→借りてる物→返すを確かめた。穴は0件。
4. **AIが見たことない文法 → クセのヒント。** if / for / return / == / 正規表現 / len() / true・null / カッコ呼びで書いたら、この言語での書き方を返す。分からない式には使える道具の一覧を添える。同じ間違いは1回だけ言う。
5. **サンプルが小さい・モデルが1つ → 3回目の実験（Haiku、各6回）。** (A) 全部通った 1/6・バグ平均3.5、(B) 1回目 3/6 → ループ後 6/6・バグ0。合わせて各条件16回。最初は1つのエージェントに6回書かせて独立でなくなったので、捨ててやり直した（EXPERIMENT.md に書いた）。

- 残る弱さ: 例と never に書いてないことは、やはり守れない（穴さがしで「書いてない所」は見えるようになった）。

## 役割（完了）

- `thing User` の `role[member | admin]` が役割になる。who に書いた役割が無ければ E28。
- 最初の管理者は `lang role`、2人目からは画面の「管理者にする」。自分は外せない（`where it is not me`）ので管理者は0人にならない。
- 入力を開くボタンは、作れる人にだけ出る。
- 備品かしだしで、member の `change` が「作る」も含んでいて、誰でも備品を足せる穴に気づいた → `move` に絞った。
- ブラウザで: hanako には「備品を足す」が無い → taro が管理者にする → hanako に出る、まで確かめた。
- まだ無いもの: 本当のログイン（今は `?user=名前`。仕様どおり connect に任せる所で、まだ作っていない）。

- テスト208件通過。

## 標準ライブラリと計算（完了）

- `use std/date`・`std/money`・`std/contact`。action 4つ（FindMonthDay / FindYen / FindEmail / FindPhone）。中身もこの言語で書き、example 29個と never で守る。
- 足した道具: 項目の書き換え `set 項目 to 値` / `do 部品 with 項目` / `result` / 画面の件数と合計 `stats` / example の `adds` と `expect 箱` / shape の `word with` / `名前 of X`。
- 作りながら見つけた言語の粗: `count of a + count of b` が `count of (a + ...)` と読まれていた（+ を一番弱く）/ 状態の名前と行の名前が同じだと黙って状態が勝つ（エラーに）/ word が日本語も拾うのでメールの前の日本語までくっつく（ASCII に）。
- 3つ目のアプリ `spec/kakeibo.lang`（家計メモ）: メモから金額を拾って合計。AIが中身を書く行は0（std の FindYen、中身27行＋契約13行をそのまま使う）。穴さがしが「メモを書いたら金額を拾う」の example が無いことを見つけた → adds を足して書いた。
- 就活Hub の ExtractDeadline は std に置き換えなかった。AIに中身を書かせる実験の題材で、テストと実験がそのまま使っているため。
- テスト221件通過。ブラウザで 3件・3,880円 の合計まで確かめた。
