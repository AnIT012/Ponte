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
