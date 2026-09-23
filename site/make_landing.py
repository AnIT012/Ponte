"""landing.html を作り直す（構文の見本 site/samples と、色付け site/highlight.py から）。

  python site/make_landing.py && python site/build.py
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from highlight import highlight, states_in  # noqa: E402

SLIDES = [
    ("1", "データの形を書く", "thing には、アプリが持つデータの形を書きます。項目の名前と型を並べておけば、保存や読み書きは Ponte が引き受けます。状態は <code>[todo | done]</code> のように、取りうる値を全部書いておきます。"),
    ("2", "流れと、誰が何をできるか", "flow には状態がどう移れるかを、who には誰が何をしてよいかを書きます。who に書いていない操作は誰にもできないので、権限の書き忘れはエラーとして見つかります。"),
    ("3", "きっかけと、やること", "rule には、きっかけとやることを一組で書きます。when に書けるのは時刻やボタンのような出来事だけで、「明日まで」のような条件は list の where で絞ります。"),
    ("4", "例がそのままテストになる", "rule の下に example を書くと、それがテストになります。<code>ponte test</code> は例が通るかを確かめるだけでなく、まだ例で確かめていないルールや状態の変化も教えてくれます。"),
    ("5", "AIに任せる部分には約束を", "処理の中身をAIに書いてもらうときは、action に入力と答えの例、してはいけないことを先に書きます。AIが書いた中身はこの約束に照らして機械で確かめられ、守れていなければ書き直しになります。"),
    ("6", "決めていないことは tbd に", "まだ決めていないことは tbd に書いておけます。tbd が残っているあいだは <code>ponte check</code> が通らないので、決め忘れたまま動き出すことはありません。"),
]
REPO = "https://github.com/AnIT012/nameless-lang"
DOC = REPO + "/blob/main/docs/"

srcs = {n: (HERE / "samples" / f"{n}.ponte").read_text(encoding="utf-8") for n, _, _ in SLIDES}
states = states_in("\n".join(srcs.values()))
items = []
for i, (n, h, p) in enumerate(SLIDES):
    hid = "" if i == 0 else " hidden"
    items.append(f'    <div class="slide"{hid}>\n      <pre class="code">{highlight(srcs[n], states)}</pre>\n'
                 f'      <div class="explain"><h2>{h}</h2><p>{p}</p></div>\n    </div>')
dots = "".join('<button type="button" data-go="%d" aria-label="見本 %d"%s>%d</button>'
               % (i, i + 1, ' aria-current="true"' if i == 0 else "", i + 1) for i in range(len(SLIDES)))
old = (HERE / "landing.html").read_text(encoding="utf-8")
head = old[:old.index("/* ---- top bar ---- */")]
body = (HERE / "page.body.html").read_text(encoding="utf-8")
body = body.replace("{REPO}", REPO).replace("{DOC}", DOC).replace("{SLIDES}", "\n".join(items)).replace("{DOTS}", dots)
(HERE / "landing.html").write_text(head + (HERE / "page.css").read_text(encoding="utf-8") + body, encoding="utf-8")
print("site/landing.html を作り直しました")
