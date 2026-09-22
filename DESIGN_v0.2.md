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

### 名前と型（小さい4つ）
- entity → **thing**
- unknown → **tbd**（小文字）
- `one of [a, b]` → **`a | b`**。flow や出力の `found | missing` と同じ書き方
- `ref User` → **`User`**。型に箱の名前を書けば別の箱を指す

### コメントは2種類
| 書き方 | 意味 |
|---|---|
| `#` | 普通のコメント。ビルドに関係無い |
| `##` | 止めるコメント。1つでも残ってたらビルドできない |

- proposed はまるごと `##` に置き換え。
- AIが仕様の穴に気づいたら、答えの案を `##` で書いて、理由を後ろの `#` に書く。
- 人は `##` を外して承認、行ごと消して却下。
- tbd との違い: tbd は答えの無い「まだ決めてないこと」、`##` は答えの案がもう書いてあるもの。

```
list DueSoon
  of    Application
  where status is draft
  where deadline within 3 days
  ## where deadline is after now    # 締切が過ぎた応募も通知する？
```

## まだ決めてないこと（小さい）
1. まとまり（group）を入れるか、1ファイル1まとまりにするか
2. do の中の一時的な状態（true/false の代わり）の名前付け

## まだ手を付けてないこと（大きい）
- 画面（screen）
- 誰ができるか（who can）
- データの保存と、項目を足した時の扱い
- 消した時の扱い
- user says のルールの example
- do の中で使える道具の一覧
- 他のAIからの指摘: ExtractDeadline の契約の矛盾（never guess the year と datetime）、by ai と ask ai の区別
