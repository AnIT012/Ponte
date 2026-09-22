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
