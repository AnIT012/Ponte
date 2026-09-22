# nameless-lang（仮）— 人とAIの間の言語 v0.1

「人は決めて、AIが書いて、言語が守る」言語の検証リポジトリ。
言語にまだ名前は無い。仕様は `docs/言語仕様_v0.1.txt`（PDFからテキスト化）。

## 使い方

```
python -m lang check spec/hub.spec        # 決めてないことを探す
python -m lang gen   spec/hub_ready.spec -o generated/hub   # Goに変換（フェーズ2）
python -m lang proposals spec/hub.spec  # AIの提案で承認待ちのもの（フェーズ4）
python experiment/run.py --dummy && python experiment/score.py   # 検証実験（フェーズ3）
python -m pytest                          # テスト
```

## ファイル

| ファイル | 中身 |
|---|---|
| `QUESTIONS.md` | 仕様の分からない点・矛盾。判断待ち |
| `PROPOSALS.md` | 仕様に無いが足したくなったこと（足していない） |
| `REPORT.md` | フェーズごとの報告 |
| `lang/parser.py` | 宣言／節の木を作る |
| `lang/checker.py` | 仕様6章のエラー12個 |
| `spec/` | 就活Hubの例（hub.spec は原文どおり＝止まる、hub_ready.spec は渡せる版） |
| `lang/codegen.py` | 決まった部分の Go 変換 |
| `generated/hub/` | hub_ready.spec からの変換結果 |
| `experiment/` | 自然文 vs 言語の実験（EXPERIMENT.md） |
| `NAMES.md` | 名前の候補と被りチェック |
| `tests/` | 壊した仕様／直した仕様のペア |
