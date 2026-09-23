"""「試す」の色分け（play.js の JS 版）が、highlight.py と同じ結果になるか。node が無ければ飛ばす。"""
import glob
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))
from highlight import highlight  # noqa: E402

NODE = shutil.which("node")


def samples():
    out = [Path(p).read_text(encoding="utf-8") for p in sorted(glob.glob(str(ROOT / "spec" / "*.ponte")))]
    for p in sorted(glob.glob(str(ROOT / "docs" / "*.md"))):
        out += re.findall(r"```(?:ponte)?\n(.*?)```", Path(p).read_text(encoding="utf-8"), re.S)
    return out


@pytest.mark.skipif(not NODE, reason="node が無い")
def test_js_highlight_matches_python():
    js = (ROOT / "site" / "play.js").read_text(encoding="utf-8")
    m = re.search(r"const HL = \(\(\) => \{.*?\n\}\)\(\);", js, re.S)
    assert m, "play.js に HL が見つからない"
    srcs = samples()
    assert len(srcs) > 20
    script = m.group(0) + "\nconst xs = JSON.parse(require('fs').readFileSync(0, 'utf8'));\nprocess.stdout.write(JSON.stringify(xs.map(HL)));"
    r = subprocess.run([NODE, "-e", script], input=json.dumps(srcs), capture_output=True, text=True, check=True)
    for src, got in zip(srcs, json.loads(r.stdout)):
        assert got == highlight(src), src[:200]
