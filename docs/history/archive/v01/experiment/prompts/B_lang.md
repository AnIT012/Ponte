# 就活Hub「メール→締切→通知」の要件（この言語）

次の仕様をそのまま実装してください。読み方：

- 行頭の語（entity / flow / list / match / rule / action）が塊の見出し。字下げした行がその中身
- `entity` はデータの形。`one of [...]` は名前の付いた状態
- `flow` は状態の流れ。`->` の通りにしか動けない。`on conflict A wins over B` は矛盾する変更が同時に来たときの勝者
- `list` は条件で絞った集まり。`where` は複数行なら全部満たす（and）。`sort by` は昇順
- `match` は値ごとの結果の表。`otherwise` はそれ以外
- `rule` は「きっかけ（when）→ やること（do）」。`example` は必ず通る例。`because` は目的
- `action` は契約だけ（入力・出力・例・禁止 never・逃げ道 else・誰が埋めるか by・どうやるか how）
- 同じ箱（entity 1件）への書き換えは1つずつ順番に、箱をまたぐ処理は並列

```
# 就活Hub「メール→締切→通知」— 渡せる版
# hub.spec から unknown / proposed / ParseApplicationMail(△・example と else が無い) を外したもの。
# unknown の答え（timezone of deadline / who can delete Application）は QUESTIONS.md Q1 で判断待ち。

entity Application
  owner:    ref User
  company:  ref Company
  deadline: datetime
  status:   one of [draft, submitted, passed, failed]

flow Application.status
  draft -> submitted -> passed | failed
  on conflict failed wins over passed

list DueSoon
  from Application
  where status is draft
  where deadline within 3 days
  sort by deadline

match Application.status to color
  draft     -> red
  submitted -> gray
  passed    -> blue
  otherwise -> gray

rule Remind
  because "締切を落とさないため"
  when every day at 21:00
  do notify user each of DueSoon
  example
    given Application(company "Osaka Gas", deadline "9/24 23:59", status draft)
    at "9/21 21:00"
    expect notify "Osaka Gas"

rule MarkSubmitted
  because "ユーザーの一言で提出済みにするため"
  when user says "submitted {company}"
  do move Application where company is {company} to submitted

action ExtractDeadline
  input   mail: Message
  output  deadline: datetime
  example "10/15(木)12:00まで" -> 10/15 12:00
  example "【締切9/24 23:59】" -> 9/24 23:59
  never   guess the year
  else    ask user
  by      ai
  how
    limit 5 seconds
    on failure retry 3 times

connect gmail
  sends new message: Message
```
