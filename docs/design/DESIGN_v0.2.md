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

### 状態は `[ ]` で並べる
- `[ ]` は「状態を並べる」専用。中の `|` は「どれか1つ（or）」。
- and の記号は作らない。and は where を行で重ねて書く。
- thing の項目も do の中の一時的な状態も同じ書き方。

```
thing Application
  status[draft | submitted | passed | failed]

action ...
  do
    day = weekday of deadline
    kind[weekend | weekday] = match day
                                saturday | sunday -> weekend
                                else              -> weekday
```

- match の右側に、宣言に無い状態を書いたらエラー（打ち間違いを止める）。
- 宣言した状態を全部書いた match なら else は省略できる。1つでも抜けていたら else は必須。

### group（まとまり）
- rule や relate などを名前で括る。継承は無い。外からは `Mail.ReadMail` で呼ぶ。
- group の中の字下げは入れ子と数えない。ただし group の中に group は書けない。

### 項目の書き方
- `名前 型` を並べるだけ。`:` は付けない。名前と型は色分けで見分ける。

```
thing Application
  company  text
  deadline date
  owner    User
  status[draft | submitted | passed | failed]
```

## まだ決めてないこと（小さい）
- 無し

## まだ手を付けてないこと（大きい）
- 画面（screen）
- 誰ができるか（who can）
- データの保存と、項目を足した時の扱い
- 消した時の扱い
- user says のルールの example
- do の中で使える道具の一覧
- 他のAIからの指摘: ExtractDeadline の契約の矛盾（never guess the year と datetime）、by ai と ask ai の区別

## DESIGN_ALL.md から決まったこと

### who
- who が1行も無い thing はエラー（渡せません）。
- 書いてないことは誰もできない。

### 画面の状態の短縮
- 画面だけの状態（メニュー、タブなど）は look の中で `toggle 状態` / `set 状態 値` と書ける。rule は要らない。
- データ（thing の項目）は今まで通り rule の move でしか変えられない。

```
look Header
  button menu-button   toggle menu
  button close-button  set menu closed
```

### 読み上げ対応
- 名前の無いボタン、説明の無い画像は、試作の間は「注意」、公開する時は「エラー」。

```
button ✓ named 提出した
image logo about 会社のロゴ
```

### DESIGN_ALL.md の残り（任されて決めたもの）
DESIGN_ALL.md の案をそのまま採用する。理由も残しておく。

| 項目 | 決めたこと | 理由 |
|---|---|---|
| 置き場所 | top / main / side / bottom / over | よくある画面はこの5つで組める。細かい時は row / column / grid がある |
| 画面の大きさ | phone / tablet / wide の3段階 | 数字で決めると迷う。名前なら読める |
| do の道具 | DESIGN_ALL B1 の一覧で始める | 既存の言語でよく使う語だけにしてある。足りなければ足す |
| 数の型 | money / percent / count を足す | お金の計算の誤差と、通貨の混ぜ間違いを言語が止められる |
| ask ai | how に上限（時間かお金）が無ければエラー | 実行の度にAIを呼ぶので、上限が無いと止まらない・高くつく |
| change | add / rename / remove。足す項目の初期値が無ければエラー | 決めてないことはエラー |
| gone | `gone[remove too \| leave empty \| block]` | 3択で全部の場合を覆える |
| connect | gives / does / needs / limit | 届く・頼む・秘密・上限で、外とのやり取りは全部書ける |
| does の結果 | 必ず状態（`sent \| failed` など） | true/false が無い原則と揃う。失敗の扱いを書き忘れない |
| example | given / 出来事 / expect の3段 | 時間・発言・タップ・外からの出来事を同じ形で書ける |

これで DESIGN_ALL.md の「決めたいこと」は全部決まった。
