"""ホームページを作る。

  python site/build.py

site/landing.html（中身）から2つ作る:
  site/index.html        … GitHub Pages 用（写真は site/img/ を見る）
  site/artifact.html     … 1ファイル版（写真を埋め込む。git には入れない）
"""
import base64
import re
import shutil
from pathlib import Path

HERE = Path(__file__).parent
SHOTS = HERE.parent / "docs" / "screenshots"
body = (HERE / "landing.html").read_text(encoding="utf-8")
names = sorted(set(re.findall(r"\{\{IMG:(\w+)\}\}", body)))

(HERE / "img").mkdir(exist_ok=True)
for n in names:
    shutil.copy(SHOTS / f"{n}.png", HERE / "img" / f"{n}.png")
page = body
for n in names:
    page = page.replace("{{IMG:%s}}" % n, f"img/{n}.png")
(HERE / "index.html").write_text(
    '<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    '<meta name="description" content="Ponte — 人は決めて、AIが書いて、言語が守る。">\n'
    "</head>\n<body>\n" + page + "\n</body>\n</html>\n", encoding="utf-8")

one = body
for n in names:
    data = base64.b64encode((SHOTS / f"{n}.png").read_bytes()).decode()
    one = one.replace("{{IMG:%s}}" % n, f"data:image/png;base64,{data}")
(HERE / "artifact.html").write_text(one, encoding="utf-8")
print("site/index.html と site/artifact.html を作りました")
