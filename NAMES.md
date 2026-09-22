# NAMES — 名前の候補10個と被りチェック

仕様8章「名前（Intent系は既存と被る可能性大。調べてから）」に従い、Intent 系は外した。
軸は「人は決めて、AIが書いて、言語が守る」。候補は日本語由来を中心にした（英語圏の既存名と被りにくい）。

調べ方: Web 検索で「<名前> programming language / software / github」。**商標DB（J-PlatPat / USPTO）は未確認**。
被りの重さ: ◎ ほぼ無し ／ ○ 同名はあるが別分野 ／ △ 同名のソフトが複数 ／ × 言語・ライブラリ名で先客あり

| # | 候補 | 由来 | 被り | 見つかったもの |
|---|---|---|---|---|
| 1 | **Sadame（さだめ）** | 定め＝人が決めたこと | ◎ | 言語・DSL では見つからず |
| 2 | **Tsumori（つもり）** | 「〜するつもり」＝意図。Intent の日本語 | ◎ | 完全一致なし（tsumugi / tsumugu という別プロジェクトはある） |
| 3 | **Hitoai（ひとあい）** | 人とAIの間 | ◎ | 見つからず |
| 4 | **Kimari（きまり）** | 決まり＝ルール | ○ | kimari-local-ai（ローカルLLM実行環境、alpha）、Kimai（時間記録）が近い |
| 5 | **Mitei（みてい）** | 未定＝unknown を第一級にする言語らしさ | ○ | GitHub ユーザー名 mitei、Mitki 言語が近い |
| 6 | **Kime（きめ）** | 決め | × | kime＝Korean IME（GitHub Riey/kime）。Kimi K2 とも紛らわしい |
| 7 | **Mamori（まもり）** | 言語が守る | × | Go の設定ライブラリ xavidop/mamori、mamori.io（セキュリティ製品）、生成AI向けプライバシー層 |
| 8 | **Yakusoku（やくそく）** | 約束＝契約（action の契約） | × | JS の Promise ライブラリが複数（kumabook/yakusoku ほか） |
| 9 | **Hako（はこ）** | 箱＝entity 1件 | × | Hako 言語（Rust にトランスパイル）、Hako JS エンジンほか多数 |
| 10 | **Contractlang** | 契約言語（英語） | △ | 完全一致なし。ただし Pact-Lang（AI エージェント向け契約言語）が同じ領域で近い |

## おすすめ
1. **Sadame** — 被り無し、意味が「人が決めた」に直結、発音しやすい
2. **Tsumori** — Intent を避けつつ同じ意味。被り無し
3. **Hitoai** — コンセプトそのもの。ただし英語圏では読みにくい

## 出典（検索結果）
- Kime: https://github.com/Riey/kime
- Mamori: https://github.com/xavidop/mamori , https://doc.mamori.io/ , https://github.com/Nananananana/mamori
- Yakusoku: https://github.com/kumabook/yakusoku , https://github.com/shimataro/yakusoku
- Hako: https://github.com/levementesalgado/Hako , https://github.com/6over3/hako
- Kimari: https://github.com/smouj/kimari-local-ai
- Mitei/Mitki: https://github.com/mitki-lang/mitki
- Contract 系: https://github.com/Pact-Lang/pact
- Tsumori 周辺: https://github.com/kannahira/tsumugi
