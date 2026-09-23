# 就活Hub「メール→締切→通知」を Python で作ってください

## 要件（日本語）

就活の応募を管理する仕組みです。使う人は複数いて、それぞれ自分の応募だけを扱います。

応募には、会社名、締切日時、状態があります。状態は「draft（下書き）」「submitted（提出済み）」「passed（通過）」「failed（不合格）」のどれかです。新しく足した応募は draft から始まります。

状態は決まった順番でしか進めません。draft から submitted へ、submitted から passed または failed へ、です。draft からいきなり passed にはできません。順番に反する変更はエラーにしてください。
通過と不合格が同時に来ることがあります。そのときは不合格を優先してください。つまり、passed になった後に failed が来たら failed に上書きし、failed になった後に passed が来ても failed のままにしてください（エラーにはしないでください）。

「締切が近い応募」とは、状態が draft で、締切が今から3日以内のものです。締切の早い順に並べてください。

状態ごとの色は、draft が orange、submitted が blue、passed が green、failed が gray、それ以外は gray です。

毎日21時に、締切が近い応募それぞれについて、その応募の持ち主に通知してください。目的は締切を落とさないためです。
例：会社「Osaka Gas」、締切「9/24 23:59」、状態が draft の応募があるとき、「9/21 21:00」に動かすと「Osaka Gas」が通知されます。

自分の応募しか見えず、自分の応募しか動かせません。

メール本文から締切を取り出す機能も必要です。入力はメール本文、出力は「月/日 時:分」の文字列（例 "10/15 12:00"）です。
例：「10/15(木)12:00まで」→ "10/15 12:00"、「【締切9/24 23:59】」→ "9/24 23:59"、「来週中にご提出ください」→ 見つからない、「9/24 23:59 または 9/30 23:59」→ 見つからない。
年は推測しないでください。自信がないとき（見つからないとき）は None を返してください（ユーザーに聞き返す合図です）。

応募1件ごとに独立して処理し、同じ応募への書き換えは1つずつ順番に行ってください（複数のスレッドから同時に呼ばれても壊れないように）。

## 作るもの

Python 3.11、標準ライブラリだけで、1つのファイルに書いてください。次の窓口（名前・引数・戻り値）は必ずこの通りにしてください。

```python
from datetime import datetime

class System:
    def __init__(self, now: datetime): ...
    def set_now(self, now: datetime) -> None: ...          # 今の時刻を変える（テスト用）
    def add(self, user: str, company: str, deadline: str) -> str: ...
        # 応募を足して id を返す。deadline は "9/24 23:59" のような「月/日 時:分」（年は今の年）
    def apps(self, user: str) -> list[dict]: ...
        # その人の応募を足した順に全部。各要素は {"id", "company", "deadline", "status"}
    def due_soon(self, user: str) -> list[dict]: ...       # その人の「締切が近い応募」（締切の早い順）
    def tick(self) -> list[tuple[str, str]]: ...
        # 今の時刻が21:00なら通知を送り、送った (持ち主, 会社名) を送った順に返す。21:00でなければ []
    def move(self, user: str, app_id: str, to: str) -> None: ...
        # 状態を動かす。順番に反する・他人の応募なら ValueError を投げる
    def color(self, status: str) -> str: ...
    def extract_deadline(self, mail: str) -> str | None: ...
```

要件に書いていないことや矛盾があって決められない場合は、コードの先頭のコメントに `# Q: ...` の形で1行ずつ書いてください（推測で埋めた箇所も書いてください）。
