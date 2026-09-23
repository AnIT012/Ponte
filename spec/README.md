# 見本のアプリ

どれも `python -m lang run spec/〇〇.lang` で動く（→ http://127.0.0.1:8000/）。

| ファイル | アプリ | 見どころ |
|---|---|---|
| `todo.lang` | やること | 入門（[docs/入門.md](../docs/入門.md)）のできあがり。一番小さい |
| `lend.lang` | 備品かしだし | 役割（`lang role spec/lend.lang taro admin` で最初の管理者）、2つの thing（Item と Loan）、rule の where、件数 |
| `kakeibo.lang` | 家計メモ | 標準ライブラリ `use std/money` で金額を拾い、`set yen to result`、合計 |
| `hub_app.lang` | 就活Hub | メールから締切を拾う action（中身は AI が書いた `hub_app.lang.ai/`）、ボード・カレンダー・英語・取り消し |
| `hub_ready.lang` | 就活Hub（小さい版） | 仕様書の付録から tbd を外したもの（公開の検査まで通る） |
| `hub.lang` | 就活Hub（付録そのまま） | tbd が残っているので **わざと止まる**（E05） |

データは `〇〇.lang.data.jsonl` に残る（git には入れない）。
