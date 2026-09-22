# 仕様 v0.2 の相談メモ（決まったこと／まだのこと）

v0.1 からの変更案。ここに書いたことは相談で合意したもの。仕様書本体にはまだ反映していない。

## 決まったこと

### 名前
- rule・match・flow はそのまま。
- else と do はどこでも同じ意味。
  - else = 普通の道が使えなかった時の、決めておいた逃げ道
  - do = やること

### flow（状態の流れ）
- 状態の流れだけを書く。動作の順番は書かない。
- ぶつかったら勝つ方は `>` で書く。

```
flow Application.status
  draft -> submitted -> passed | failed
  failed > passed
```

### action の中身（do）
- `名前 = 式` と、名前を付けた match だけ書ける。
- match の中に match は禁止（入れ子）。

### ルール同士の関係（relate）
全部の行が「左が先、右が後」。

| 書き方 | 意味 |
|---|---|
| `A then B` | Aが終わったらBが動く |
| `A then no B` | Aをやったら、この後Bは動かない。Bがもう済んでいても取り消さない |
| `A before B` | Bが動く時、Aは済んでいる。Aが終わってもBは勝手に動かない |
| `A > B` | 同時に当てはまったらAが勝つ |
| `A else B` | Aが失敗したらBをやる |

```
relate
  ReadMail     then    FileMail
  ManualAdd    then no FileMail
  CheckSpam    before  FileMail
  NotifyFailed >       Remind
  LineNotify   else    MailNotify
```

チェッカーで止めるもの:
- then / before をつないで一周する（循環）
- `A > B` と `B > A` が両方ある（矛盾）
- `A before B` なのに A が起きえない（B が永遠に待つ）
- action に else があり、relate でも同じ action に else がある（逃げ道が2つ）

## まだ決めてないこと（小さい）
1. entity を thing にするか
2. unknown を tbd にするか
3. `one of [a, b]` を `a | b` にするか、`ref` を消すか
4. proposed を行頭の `?` にするか
5. まとまり（group）を入れるか、1ファイル1まとまりにするか
6. do の中の一時的な状態（true/false の代わり）の名前付け

## まだ手を付けてないこと（大きい）
- 画面（screen）
- 誰ができるか（who can）
- データの保存と、項目を足した時の扱い
- 消した時の扱い
- user says のルールの example
- do の中で使える道具の一覧
- 他のAIからの指摘: ExtractDeadline の契約の矛盾（never guess the year と datetime）、by ai と ask ai の区別
