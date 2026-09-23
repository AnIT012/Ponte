# 手を入れる時

## まず

```
python -m pytest                               # 全部通ること
python -m ponte guide --spec                    # 仕様書 10章の道具の表を実装に合わせる
```

依存は増やさない（Python 3.11 の標準機能だけ）。

## よくある手の入れ方

### 道具を1つ足す（do の中で使うもの）
1. `ponte/body.py` の `_eval` に書き方を足す。
2. 同じファイルの `TOOLS` に1行足す（種類・書き方・意味・**動く例**・例の入力・答え）。
3. `python -m ponte guide --spec` で仕様書の表を更新。
   → AIへの説明・エラーの一言・仕様書に自動で載り、例は `tests/test_guide.py` が動かして確かめる。

### rule の書き方を足す（when / do / 値）
1. `ponte/forms.py` の一覧に1行足す（正規表現・書き方・意味・例）。
2. 実行エンジン（`ponte/runtime.py`）で本当に動くようにする。**動かないものは一覧に入れない**（when は `False` を付けると check が止める）。
3. 型の確かめが要るなら `ponte/checker.py` の `check_types`。

### エラーを1つ足す
1. `ponte/checker.py` に関数を1つ書き、`ALL_CHECKS` に足す。
2. `tests/make_cases.py` に「壊した仕様」と「直した仕様」の組を足して `python tests/make_cases.py`。
3. 仕様書 13章に1行。

### 標準ライブラリを足す
1. `ponte/std/名前.ponte` に action（契約）、`ponte/std/body/` に中身。
2. example を多めに（2つ以上あったら決めない、全角、空の時も）。never も付ける。
3. `tests/test_std.py` が std の全部を自動で流す。

## 書き方の約束

- エラーの文は「何が・どこで・どう直す」を1文で。やさしい日本語で。
- コメントは「なぜ」を書く。
- 見本のアプリ（`spec/*.ponte`）は全部、check と test を通ったまま保つ（`tests/test_docs.py`）。
