# 手を入れるとき

## 最初に

```
python -m pytest                               # 全部通ること
python -m ponte guide --spec                    # 仕様書 10章（道具）と 13章（エラー）の表を実装に合わせる
python site/make.py && python site/build.py     # ホームページを docs と実装に合わせる
```

依存は増やしません。使うのは Python 3.11 の標準機能だけです。

## よくある変更

### 道具を1つ足す（do の中で使うもの）

1. `ponte/body.py` の `_eval` に書き方を足します。
2. 同じファイルの `TOOLS` に1行足します。種類、書き方、意味、動く例、例の入力、答えを書きます。
3. `python -m ponte guide --spec` で仕様書の表を更新します。

これで AI への説明、エラーの一言、仕様書に自動で載ります。例は `tests/test_guide.py` が実際に動かして確かめます。

### rule の書き方を足す（when / do / 値）

1. `ponte/forms.py` の一覧に1行足します（正規表現、書き方、意味、例）。
2. 実行エンジン（`ponte/runtime.py`）で実際に動くようにします。**動かないものは一覧に入れません。** when に `False` を付けると、check がエラーにします。
3. 型の確認が必要なら `ponte/checker.py` の `check_types` に足します。

### エラーを1つ足す

1. `ponte/checker.py` に関数を1つ書き、`ALL_CHECKS` に足します。
2. `tests/make_cases.py` に「壊した仕様」と「直した仕様」の組を足し、`python tests/make_cases.py` を実行します。
3. `ponte/errors.py` の `ERRORS` に1行足します（一言、なぜ止めるか、どう直すか）。ないと `tests/test_errors.py` が失敗します。
4. `python -m ponte guide --spec` で仕様書 13章を、`python site/make.py && python site/build.py` でホームページを更新します。

### 標準ライブラリを足す

1. `ponte/std/名前.ponte` に action（契約）を書き、`ponte/std/body/` に中身を置きます。
2. example は多めに書きます。候補が2つ以上あって決められない場合、全角の入力、空の入力なども入れます。never も付けます。
3. `tests/test_std.py` が std のすべてを自動で流します。

## 書き方の約束

- エラーの文は「何が、どこで、どう直すか」を1文で、やさしい日本語で書きます。
- コメントには「なぜ」を書きます。
- 見本のアプリ（`spec/*.ponte`）は、すべて check と test を通る状態に保ちます（`tests/test_docs.py`）。
- todo / lend / kakeibo を変えたら、`ponte/templates/` にも写します。これは `ponte new --from` のひな形で、ずれるとテストが失敗します。
- 日本語の文章は [docs/文章の書き方.md](docs/文章の書き方.md) に沿って書きます。
