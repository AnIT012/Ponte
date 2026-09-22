# AI の代わりの返事

この環境には ANTHROPIC_API_KEY が無いので、`python -m lang fill` の「AI」の役を、
このリポジトリを作っているセッションの Claude が引き受けて、ループが送るのと同じプロンプトを読んで返事を書いた。

- 返事を書いたのは人ではなく AI（Claude）。ただし API 経由ではない。
- 確かめたのは機械（パーサー・チェッカー・example・never）。返事の良し悪しを人が手で判定していない。
- キーを入れれば `python -m lang fill spec/hub_app.lang` で本物の API に同じことをさせられる。

使い方:
```
python -m lang fill spec/hub_app.lang --ai file:experiment/ai_replies/ExtractDeadline
```
