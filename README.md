# Ponte（ポンテ）

<img src="docs/logo/ponte.svg" alt="Ponte" width="96">

[English](README.en.md)

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

![備品かしだし](docs/screenshots/lend_home.png)

---

## 30秒で

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
git clone https://github.com/AnIT012/nameless-lang
cd nameless-lang
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
| `action` | AI が中身を書く部分。`example`、`never`、`else` の契約を付ける |
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
| `tests/` | テスト（320件ほど） |
| `docs/` | 仕様書、入門、しくみ、設計の判断、画面の写真 |
| `site/` | ホームページ。`python site/make.py && python site/build.py` で作り、main に入ると GitHub Pages に出る |
| `experiment/` | 比較実験（プロンプト、AI の返答、採点） |
| `editor/vscode/` | エディタの色分けと、保存時のエラー表示 |
| `archive/v01/` | 最初の版（当時のまま） |

記録は次のとおりです。

- [CHANGELOG.md](CHANGELOG.md): 何が入ったか
- [REPORT.md](REPORT.md): 作業の記録
- [REVIEW.md](REVIEW.md): 弱いパーツと欲しいもの
- [docs/DECISIONS.md](docs/DECISIONS.md): 設計の判断

手を入れる場合は [CONTRIBUTING.md](CONTRIBUTING.md) を読んでください。

## 現在の制限

- ログインは合言葉だけです。`ponte run --login` で、名前と合言葉によるログインになります（`--login` なしで外に開こうとすると止まります）。メールでの確認や、合言葉を忘れたときの手続きはまだありません。
- example と never に書いていないことは守れません。穴さがしで「書いていない部分」は見えますが、書くのは人です。
- 道具はまだ少なめです。each、group by、json などは「まだない道具」として、書くとエラーになります。
- 外への通知は、まだ画面の中だけです。メールや LINE に送る部分（connect の does）は形だけで、実際につなぐのは中身の仕事です。
- 地図は出せません。画像は `image` で出せます。
- 1台で動かす前提です。データは1つのファイルに追記します。たくさんの人が同時に使う大きなサービスには向きません。
