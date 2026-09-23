# 見本のアプリ

どれも `python -m ponte run spec/〇〇.ponte` で動く（→ http://127.0.0.1:8000/）。

| ファイル | アプリ | 見どころ |
|---|---|---|
| `todo.ponte` | やること | 入門（[docs/入門.md](../docs/入門.md)）のできあがり。一番小さい |
| `lend.ponte` | 備品かしだし | 役割（`ponte role spec/lend.ponte taro admin` で最初の管理者）、2つの thing（Item と Loan）、rule の where、件数 |
| `kakeibo.ponte` | 家計メモ | 標準ライブラリ `use std/money` で金額を拾い、`set yen to result`、合計 |
| `hub_app.ponte` | 就活Hub | メールから締切を拾う action（中身は AI が書いた `hub_app.ponte.ai/`）、ボード・カレンダー・英語・取り消し |
| `hub_ready.ponte` | 就活Hub（小さい版） | 仕様書の付録から tbd を外したもの（公開の検査まで通る） |
| `hub.ponte` | 就活Hub（付録そのまま） | tbd が残っているので **わざと止まる**（E05） |

データは `〇〇.ponte.data.jsonl` に残る（git には入れない）。
