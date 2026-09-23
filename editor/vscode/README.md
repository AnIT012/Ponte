# エディタの色分け（VS Code）

仕様書 7章の色分けを VS Code で出す。依存は無い（文法ファイル1つと設定だけ）。

入れ方: このフォルダを `~/.vscode/extensions/nameless-lang` にコピーして VS Code を開き直す。`.lang` のファイルに色が付く。

| 種類 | 色 |
|---|---|
| 見出し（thing / rule ...） | 紫・太字 |
| 節（of / when / do ...） | グレー |
| 守り（never / else / tbd / gone / > / confirm） | 赤 |
| 型（text / date / [a \| b] ...） | 緑 |
| 名前（Application ...） | 青 |
| 値（"..." / 21:00 / 3 days） | 黄 |
| コメント | 薄グレー斜体 |
| `##`（止めるコメント） | 赤の背景 |
