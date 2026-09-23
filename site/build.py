"""ホームページを作る。

  python site/make.py && python site/build.py

site/landing.html と *.src.html（中身。make.py が作る）から:
  site/index.html        … GitHub Pages 用（learn.html・reference.html も。写真は site/img/ を見る）
  site/artifact.html     … トップの1ファイル版（写真を埋め込む。git には入れない）
"""
import base64
import re
import shutil
from pathlib import Path

HERE = Path(__file__).parent
SHOTS = HERE.parent / "docs" / "screenshots"
PAGES = {"landing.html": "index.html", "learn.src.html": "learn.html", "reference.src.html": "reference.html",
         "spec.src.html": "spec.html", "how.src.html": "how.html"}
DESC = "Ponte — 人は決めて、AIが書いて、言語が守る。"


def wrap(body: str) -> str:
    return ('<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            f'<meta name="description" content="{DESC}">\n'
            "</head>\n<body>\n" + body + "\n</body>\n</html>\n")


(HERE / "img").mkdir(exist_ok=True)
bodies = {src: (HERE / src).read_text(encoding="utf-8") for src in PAGES}
for src, out in PAGES.items():
    body = bodies[src]
    for n in sorted(set(re.findall(r"\{\{IMG:(\w+)\}\}", body))):
        shutil.copy(SHOTS / f"{n}.png", HERE / "img" / f"{n}.png")
        body = body.replace("{{IMG:%s}}" % n, f"img/{n}.png")
    (HERE / out).write_text(wrap(body), encoding="utf-8")

one = bodies["landing.html"]
for n in sorted(set(re.findall(r"\{\{IMG:(\w+)\}\}", one))):
    data = base64.b64encode((SHOTS / f"{n}.png").read_bytes()).decode()
    one = one.replace("{{IMG:%s}}" % n, f"data:image/png;base64,{data}")
(HERE / "artifact.html").write_text(one, encoding="utf-8")
print("site/index.html・" + "・".join(v for v in PAGES.values() if v != "index.html") + "・artifact.html を作りました")
