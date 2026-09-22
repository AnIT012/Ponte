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
