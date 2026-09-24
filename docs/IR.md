# IR と共通テスト

Ponte は、Python や Java などの今までの言語を「下の層」として使います。
このページは、下の層を増やすための土台である IR（中間の形）と、共通テストについて書いたものです。
今の下の層は Python だけです。JavaScript / TypeScript、Go、Java はこれから作ります。

## 1. 考え方

```
.ponte  ──ponte check──▶  IR（JSON）  ──▶  Python の実装（いまの実行エンジン。基準）
                              │        ──▶  JavaScript / TypeScript の実装（これから）
                              │        ──▶  Go、Java の実装（これから）
                              └── 共通テスト ──▶ どの実装にも同じものを当てる
```

- チェックは Ponte の側で1回だけ行います。IR は `ponte check` を通った仕様からしか作れません。どの言語に移しても、決めていないことは同じように止まります。
- 下の層の実装は、IR を読んで動けば十分です。Ponte の文法を読み直す必要はありません。
- 「言語が守る」を、言語をまたいで保証するのが共通テストです。仕様の example をすべて、どの実装にも当てられる形で書き出します。共通テストをすべて通った実装だけが、Ponte の実装と名乗れます。
- 実装を人が書いても、AI に書かせても、確かめ方は同じです。

## 2. 使い方

```
$ python -m ponte ir spec/todo.ponte -o todo.ir.json
Wrote todo.ir.json (4 shared tests)

$ python -m ponte conform todo.ir.json
  pass  rule Finish (L43)
  pass  rule Reopen (L57)
  pass  rule Remind (L70)
  pass  rule OpenAdd (L81)
4 shared tests, 4 passed
```

- `ponte ir 仕様.ponte` は IR を出します。`--cases` を付けると共通テストだけを出します。
- `ponte conform IR.json` は、IR の共通テストを基準の実装（Python の実行エンジン）で流します。ほかの言語の実装は、これと同じ結果になることを目指します。

## 3. IR の中身

IR は1つの JSON です。`ponte_ir` は形の版で、今は `1` です。

| キー | 中身 |
|---|---|
| `source` | 仕様の全文（`use` で読んだものも含む）。`from_ir` はこれを読み直すので、何も失いません |
| `sha256` | `source` のハッシュ。どの仕様から作った IR かを確かめるのに使います |
| `things` | データの形。thing ごとに項目の名前、型、状態（`states`）、指した先が消えたときの扱い（`gone`） |
| `flows` | 状態の流れ。矢印（`edges`）と、同時に来たときに勝つ側（`wins`） |
| `who` | 誰が何をできるか。`role`、`can`（see / change / create / remove / move）、`thing`、`where` |
| `lists` | 条件で絞った一覧。`of`、`where`、`sort` |
| `rules` | ルール。`when`、`where`、`do`、`examples`（手順の形。4章） |
| `relate` | ルール同士の関係 |
| `actions` | action の約束。`in`、`out`、`examples`、`never`、`else`、`by`、その場で書いた `do` |
| `bodies` | 別のファイルに書いた action の中身（`by code` / `by ai`）。IR だけで完結させるために入れています。`by python` の中身は下の層のコードです。IR には入れず、`by` の文字だけを持ちます |
| `matches` | 値ごとの結果 |
| `cases` | 共通テスト（4章） |
| `tree` | すべての行を `{keyword, text, line, children}` の木にしたもの |

条件や式（`where status is todo`、`move this to done` など）は、仕様に書いたままの文字で入っています。
意味は [言語仕様](言語仕様_v0.3.md) で決まっています。下の層の実装は、この文字を仕様どおりに読みます。

## 4. 共通テストの形

共通テストは3種類です。

| `kind` | 中身 | 通る条件 |
|---|---|---|
| `rule` | `rule` の名前と、example の手順（`steps`） | 手順どおりに動かして、`expect` がすべて当たる |
| `action` | `action` の名前、入力（`input`）、期待する答え（`expect`） | 中身がその入力でその答えを返す |
| `never` | `action` の名前と、してはいけないこと（`never`） | 中身がそれをしない |

rule の手順は、1つずつ `{kind, text, values, line}` の形です。

```json
{"kind": "given",  "text": "Task",                "values": {"title": "牛乳を買う", "status": "todo"}}
{"kind": "taps",   "text": "done-button on Task", "values": {"title": "牛乳を買う"}}
{"kind": "expect", "text": "Task is done",        "values": {"title": "牛乳を買う"}}
```

`kind` は `given`（前の状態）、`adds`（人が作った）、`at`（時刻）、`says`、`taps`（ボタンを押した）、`gets`（外から届いた）、`expect`（期待する結果）のどれかです。
意味は言語仕様の 9章（テスト）のとおりです。

`ponte test` も、この手順の形をそのまま流しています（`examples.run_steps`）。
そのため、共通テストと `ponte test` の結果がずれることはありません。

中身がまだない action（たとえば `by ai` でまだ書かせていないもの）は、`ponte test` と同じく飛ばします。

## 5. 新しい言語の実装を作るとき

1. IR を読み、`things`、`flows`、`who`、`rules` などを、その言語のデータの形にします。
2. 式と条件を、言語仕様どおりに動くように実装します。
3. 共通テストを流す仕組みを作り、`ponte conform` と同じくすべて通ることを確かめます。
4. 見本の仕様（`spec/`）すべての IR で通ることを、その実装の CI で確かめます。

## 6. 確かめていること

`tests/test_ir.py` は次のことを確かめています。

- 見本の仕様すべてで、IR にして戻しても example の結果が変わらない（JSON を実際に通す）
- 見本の仕様すべてで、共通テストが基準の実装で通る
- action の中身をわざと壊すと、共通テストが失敗する
- ルールをわざと変えると、共通テストが失敗する
- 決めていないことが残る仕様からは IR を作れない
