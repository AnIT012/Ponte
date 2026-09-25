# Ponte（ポンテ）

<img src="docs/logo/ponte.svg" alt="Ponte" width="96">

**[サイト](https://anit012.github.io/Ponte/)** ・ **[ブラウザで試す](https://anit012.github.io/Ponte/play.html)** ・ [白紙から書く](https://anit012.github.io/Ponte/write.html) ・ [English](README.en.md)

> Ponte はイタリア語で「橋」という意味です。人と機械のあいだ、人と AI のあいだにかける橋という意味を込めています。

**決めるのは人。守るのは言語。**

Ponte は、プログラムのいちばん上の層に書く言語です。
書くのは「何が欲しいか」「何をしてはいけないか」「何がまだ決まっていないか」だけで、「どうやるか」は書きません。
Python や Java のような今までの言語は、Ponte の下で動く層になります。

- 書いたことは、必ず守られる約束になります。決めていないことが残っていれば動かず、書いていない操作は誰にもできず、例に合わないものは通りません。
- 覚える言葉は少なく、自分だけで書いても完結します。計算や判定の中身も、Ponte の `do` で書けます。
- AI と作るときは、同じ仕様が AI への指示になり、AI が守る約束になります。日本語の指示と違って、解釈がずれればエラーで止まります。
- 下の層に任せた部分にも約束が届きます。`with` で渡した値を下の層に「実際に使った値」として報告させ、`confirm` で照合します。渡した値が下で黙って捨てられていれば止まります。

いまは Python 3.11 の標準機能だけで動きます（ライブラリは必要ありません）。JavaScript / TypeScript、Go、Java を下の層として選べるようにする準備を進めています。
エラーや出力は英語で出ます。日本語にしたいときは `--lang ja` を付けるか、`PONTE_LANG=ja` にします。

## なぜ作ったか

- AI に開発を任せると、人が決めていない部分を AI が推測で埋めてしまいます。後から見つけて直す手間が、何度も発生していました。
- 自然言語の指示には曖昧さが残り、コードは読み書きできる人が限られます。
- 研究では、渡したはずの学習率がライブラリの中で黙って捨てられ、2日分の実験が無効になりました。エラーは一度も出ませんでした。

問題は書き方ではなく、「決めたことが本当に守られたかを確かめる手段がない」ことでした。
Ponte は、決めたことを書き、それが守られたかを言語が確かめるためのものです。

## 設計で決めたこと、作らなかったこと

| | 判断 | 理由 |
|---|---|---|
| 決めた | 決めていないことが残っていれば動かさない（`tbd`） | 推測で埋められるのを防ぐため |
| 決めた | 書いていない操作は誰にもできない（`who`） | 権限の書き忘れを、動かす前に見つけるため |
| 決めた | 例がそのままテストになる（`example`） | 決めたことを、確かめられる形で残すため |
| 決めた | 下の層が実際に使った値を報告させ、宣言と照合する（`confirm`） | 渡したつもりの値が黙って捨てられる事故を止めるため |
| 作らなかった | GUI（ボタンやフォームで組み立てる形） | 書く言語のまま、覚えることを減らすため。見出しを書くと必須の部品の名前だけが入る形にとどめた |
| 作らなかった | AI を前提にした作り | AI の使い方は変わっていくため。AI なしで完結し、使うときは同じ仕様が AI への指示になる |
| 作らなかった | 研究専用の機能 | 研究で見つけた事故は、アプリや外部 API でも起きる同じ形だったため。言語の中核として一般の仕組みにした |

設計の判断の細かい記録は [docs/DECISIONS.md](docs/DECISIONS.md) にあります。実装は AI コーディングツールで行い、設計と判断は作者が行っています。

## 例: 渡した値が、下で本当に効いたか

学習スクリプトに `lr=` を書き忘れた、実際にあった事故を再現したものです。

```
job Train
  run      uv run python train.py
  with     learning_rate 1.25e-4, batch_size 32
  confirm  learning_rate, batch_size             # 実際に使われた値と照合する
  require  test_accuracy at least 52             # 結果の条件
  suspect  test_accuracy above 75                # 良すぎる数字は止める
```

```
$ ponte job train.ponte Train
job Train: running
  confirm learning_rate: declared 1.25e-4, but 0.001 was actually used (stopped the run)
job Train: contract broken (1 problem(s))
```

学習を待たずに、その場で止まります。`train.py` の側は `report(learning_rate=lr_of(optimizer))` の1行で、optimizer が本当に持っている値を報告します。

## アプリの例

1つのファイルが、ログイン付きの Web アプリとしてそのまま動きます。

![備品かしだし](docs/screenshots/lend_home.png)

```
thing Item
  name    text
  status  [free | lent | broken]

rule Borrow
  why   空いている備品を借りる
  when  user taps borrow-button on Item
  where status is free
  do    create Loan
          item  this
          due   7 days from now
  example
    given Item
      name    "カメラ"
      status  free
    taps borrow-button on Item
      name "カメラ"
    expect Item is lent
      name "カメラ"
```

打ち間違いも決め忘れも、動かす前にエラーになります。

```
$ python -m ponte check todo.ponte
Stopped: 1 error(s)
  todo.ponte:20  E32  rule Finish: Task has no state named "finished" (todo / done)
  (how to fix: ponte explain E32)
```

example で確かめていない部分も一覧で示します。

```
$ python -m ponte test todo.ponte
Untested parts (not covered by any example: 3)
  rule Finish: has when but no example
  flow Task.status: no example covers todo -> done
```

## 比較実験

同じアプリを「日本語で頼む」場合と「Ponte で頼む」場合とで、AI に16回ずつ書かせました。
結果には、同じ14個の隠しテストを当てています（[EXPERIMENT.md](EXPERIMENT.md)）。

| | 日本語で頼む | Ponte で頼む |
|---|---|---|
| すべて通った（Sonnet、2回目の条件） | 3/5 | 5/5 |
| すべて通った（Haiku） | 1/6 | 6/6 |
| AI が推測で埋めた箇所 | 1回あたり約6個 | 0 |
| AI が書いた行数 | 約170行 | 約20行 |

Ponte の側は、1回目で間違えても言語がエラーを返すため、AI が自分で直せます。表の数字は、この直しのループを回した後のものです。
弱い点も [EXPERIMENT.md](EXPERIMENT.md) に書いています。

---

## はじめる

```
git clone https://github.com/AnIT012/Ponte
cd Ponte
python -m ponte run spec/todo.ponte        # → http://127.0.0.1:8000/

pip install -e .                           # 入れると `ponte run spec/todo.ponte` だけで動く（依存は増えない）
```

1歩ずつ作るなら [docs/入門.md](docs/入門.md) を読んでください。やることアプリを、エラーを見ながら作ります。

## コマンド

| コマンド | すること |
|---|---|
| `python -m ponte new myapp` | ひな形から新しいアプリを作る。最初から check も test も通る。`--from lend` で見本のアプリから作る |
| `python -m ponte check 仕様.ponte` | 決めていないことや間違いを探す（エラー32種）。`--json` で機械向けに出す |
| `python -m ponte test 仕様.ponte` | example と never をすべて流し、確かめていない部分（穴）も出す。`--strict` で穴も失敗にする |
| `python -m ponte run 仕様.ponte` | ブラウザの画面つきで動かす。人に使ってもらうなら `--login` を付ける（`--signup` で画面から登録もできる）。作っている間は `--reload` で書き直すたびに読み直す |
| `python -m ponte user add 仕様.ponte 名前` | ログインする人を足す。合言葉は scrypt で保存する |
| `python -m ponte explain E32` | エラーの意味と直し方を出す。コードを省くと一覧を出す |
| `python -m ponte fill 仕様.ponte` | AI に action の中身を書かせ、機械で確かめる。`ANTHROPIC_API_KEY` が必要 |
| `python -m ponte guide` | AI に渡す書き方の説明を出す。実装から作るため、実装とずれない。`--rules` で rule の書き方を出す |
| `python -m ponte train 仕様.ponte` | `model` を、保存したレコード（か `--csv`）から学ぶ。取り置いたレコードでの正解率が `require` に届かなければ使えない（[見本](spec/churn.ponte)） |
| `python -m ponte job 仕様.ponte 名前` | `job` を走らせ、下の層のプログラムが報告した事実を約束（`confirm`、`require`、`suspect`）と照合する。`confirm` がズレたら、その場で止める |
| `python -m ponte ir 仕様.ponte` | check を通った仕様を、下の層の言語に渡す中間の形（IR、JSON）にする。`--cases` で共通テストだけを出す（[docs/IR.md](docs/IR.md)） |
| `python -m ponte conform IR.json` | IR の共通テストを、基準の実装（Python）で流す |
| `python -m ponte fmt 仕様.ponte` | 見た目を整える。意味が変わる場合は書き換えない |
| `python -m ponte build 仕様.ponte` | 1つのファイル（.pyz）にまとめる。`python app.pyz` で動く |
| `python -m ponte role 仕様.ponte 名前 admin` | 最初の管理者を決める |
| `python -m ponte data export 仕様.ponte` | 保存したデータを JSON で出す（`--csv フォルダ` で Excel 向けの CSV）。`data import 仕様 Thing 表.csv` で CSV から取り込む。取り込む前にすべて確かめる。`data compact` で、伸び続ける記録を今の中身に詰める |
| `python -m ponte doc 仕様.ponte` | 仕様を、コードを読まない人にも読める1枚の HTML にまとめる。データ、流れ、権限、ルールと理由、AI に任せた部分、残っていることが載る |
| `python -m ponte lsp` | エディタ向けの言語サーバーを起動する。エラー、説明、補完を出す（設定は [editor/vscode/README.md](editor/vscode/README.md)） |
| `python -m pytest` | 言語そのもののテストを流す |

## 見本のアプリ

| アプリ | 見どころ | |
|---|---|---|
| [spec/todo.ponte](spec/todo.ponte) やること | 入門のできあがり。いちばん小さい | ![](docs/screenshots/todo.png) |
| [spec/lend.ponte](spec/lend.ponte) 備品かしだし | 役割（管理者）、2つの thing のつながり、rule の where、件数 | ![](docs/screenshots/lend_members.png) |
| [spec/kakeibo.ponte](spec/kakeibo.ponte) 家計メモ | 標準ライブラリ（`use std/money`）で金額を拾って合計する | ![](docs/screenshots/kakeibo.png) |
| [spec/hub_app.ponte](spec/hub_app.ponte) 就活Hub | メールから締切を拾う action（中身は AI が書いた）、ボード、カレンダー、英語 | ![](docs/screenshots/board.png) |

## 言語の構成

| パーツ | 書くこと |
|---|---|
| `thing` | データの形。`status [draft \| submitted]` のような状態も書く |
| `flow` | 状態の流れ（`draft -> submitted`）と、ぶつかったときにどちらを優先するか（`failed > passed`） |
| `who` | 誰が何をできるか。書いていないことは誰もできない |
| `list` | 条件で絞った一覧 |
| `rule` | きっかけと、そのときにすること（1つだけ）。`example` で確かめる |
| `relate` | rule 同士の関係（`then` / `then no` / `before` / `>` / `else`） |
| `action` | 計算や判定の部品。`example`、`never`、`else` の約束を先に書き、中身は `do` か `by python` で書く（`by ai` で AI に任せることもできる） |
| `model` | レコードから学んで状態を当てる部品。当てるもの、見てよい項目、合格の条件、使えないときを書く |
| `job` | 下の層のプログラム（学習など）を、約束（`confirm` / `require` / `suspect`）付きで走らせる |
| `connect` | 外部サービスとの境界。`with` / `confirm` で、渡した設定が効いたかを照合できる |
| `scene` / `look` / `part` / `input` / `style` / `words` | 画面、見せ方、部品、入力、見た目、言葉（日本語と英語） |
| `use std/...` | 標準ライブラリ（日付、金額、メール、電話） |
| `tbd` / `##` | まだ決めていないこと。残っていると動かない |

詳しくは [仕様書 v0.3](docs/言語仕様_v0.3.md) を参照してください。

## リポジトリの構成

| 場所 | 中身 |
|---|---|
| `ponte/` | 言語の本体（パーサ、チェッカー、実行エンジン、画面、AI による穴埋め）。[docs/仕組み.md](docs/仕組み.md) を参照 |
| `ponte/std/` | 標準ライブラリ。中身も Ponte で書いている |
| `spec/` | 見本のアプリ |
| `tests/` | テスト（490件ほど） |
| `docs/` | 仕様書、入門、しくみ、設計の判断、画面の写真 |
| `site/` | ホームページ。`python site/make.py && python site/build.py` で作り、main に入ると GitHub Pages に出る |
| `experiment/` | 比較実験（プロンプト、AI の返答、採点） |
| `editor/vscode/` | エディタの色分けと、保存時のエラー表示 |
| `docs/history/` | 作業の記録と、最初の版（当時のまま） |

記録は次のとおりです。

- [CHANGELOG.md](CHANGELOG.md): 何が入ったか
- [docs/history/REPORT.md](docs/history/REPORT.md): 作業の記録
- [docs/history/REVIEW.md](docs/history/REVIEW.md): 弱いパーツと欲しいもの
- [docs/DECISIONS.md](docs/DECISIONS.md): 設計の判断

手を入れる場合は [CONTRIBUTING.md](CONTRIBUTING.md) を読んでください。

## 現在の制限

- ログインは合言葉だけです。`ponte run --login` で、名前と合言葉によるログインになります（`--login` なしで外に開こうとすると止まります）。メールでの確認や、合言葉を忘れたときの手続きはまだありません。
- example と never に書いていないことは守れません。穴さがしで「書いていない部分」は見えますが、書くのは人です。
- 道具はまだ少なめです。each、group by、json などは「まだない道具」として、書くとエラーになります。
- 外への通知は、まだ画面の中だけです。メールや LINE に送るには、connect の中身を `by python` で書く必要があります。
- 地図は出せません。画像は `image` で出せます。
- 1台で動かす前提です。データは1つのファイルに追記します。たくさんの人が同時に使う大きなサービスには向きません。
