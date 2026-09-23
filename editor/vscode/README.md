# エディタ（VS Code）

色分けと、保存した時のエラー表示。依存は無い（文法ファイル・設定・extension.js だけ）。

入れ方: このフォルダを `~/.vscode/extensions/nameless-lang` にコピーして VS Code を開き直す。`.ponte` のファイルに色が付く。

**エラー表示。** 保存すると `python -m ponte check --json` を流して、エラーの行に波線を出す（直し方も一緒に）。ponte が入った Python を使うので、`pip install -e .` しておくか、このリポジトリをワークスペースとして開く。Python の場所は設定の `ponte.python` で変えられる。

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
