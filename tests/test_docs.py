"""ドキュメントに書いたコードと出力が、本当にその通りになるか。"""
import re

from ponte.checker import check
from ponte.examples import holes, run_examples
from ponte.parser import parse, parse_file

DOC = open("docs/入門.md", encoding="utf-8").read()
BLOCKS = re.findall(r"```\n(.*?)```", DOC, re.S)


def code(i):
    return BLOCKS[i]


def findings(src):
    return [f"todo.ponte:{f.line}  {f.code}  {f.message}" for f in check(parse(src)) if f.is_error]


def test_tutorial_outputs_are_real():
    step1 = code(0)
    step2 = step1 + "\n" + code(2)
    step3 = step2 + "\n" + code(3)
    for src in (step1, step3):
        for line in findings(src):
            assert line in DOC, line
    fixed = step3.replace("move this to finished", "move this to done")
    assert findings(fixed) == []
    s = parse(fixed)
    for h in holes(s, run_examples(s)):
        assert f"todo.ponte:{h.line}  {h.message}" in DOC, h.message
    step5 = fixed + "\n" + [b for b in BLOCKS if "due within 1 days" in b and "rule Remind" in b][0]
    for line in findings(step5):
        assert line in DOC, line


def test_finished_tutorial_app_has_no_holes():
    s = parse_file("spec/todo.ponte")
    assert [f for f in check(s) if f.is_error] == []
    res = run_examples(s)
    assert all(r.ok for r in res) and holes(s, res) == []


def test_every_sample_app_passes_check_and_test():
    import glob
    for p in sorted(glob.glob("spec/*.ponte")):
        if p.endswith("spec/hub.ponte"):          # 仕様書の付録そのまま（tbd で止まるのが正しい）
            continue
        s = parse_file(p)
        assert [f for f in check(s) if f.is_error] == [], p
        assert all(r.ok for r in run_examples(s)), p


def test_homepage_samples_are_real_ponte():
    """ホームページに載せた構文の見本（site/samples）は本物。6番は tbd の見本なので E05 だけで止まる"""
    import glob
    src = "\n".join(open(p, encoding="utf-8").read() for p in sorted(glob.glob("site/samples/[1-5].ponte")))
    assert [f.code for f in check(parse(src)) if f.is_error] == []
    six = open("site/samples/6.ponte", encoding="utf-8").read()
    assert [f.code for f in check(parse(src + "\n" + six)) if f.is_error] == ["E05"]
    page = open("site/landing.html", encoding="utf-8").read()
    for p in sorted(glob.glob("site/samples/*.ponte")):
        first = open(p, encoding="utf-8").read().splitlines()[0]
        assert first in page, p


def test_homepage_is_generated_from_docs_and_code():
    """site/ の中身は docs と実装から作る。ずれていたら python site/make.py && python site/build.py"""
    import importlib.util
    import sys
    sys.path.insert(0, "site")
    spec = importlib.util.spec_from_file_location("site_make", "site/make.py")
    make = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(make)
    from pathlib import Path
    assert Path("site/landing.html").read_text(encoding="utf-8") == make.landing()
    assert Path("site/learn.src.html").read_text(encoding="utf-8") == make.doc_page(Path("docs/入門.md"), "入門 — やることアプリを作る", "learn")
    assert Path("site/reference.src.html").read_text(encoding="utf-8") == make.reference()
    for name, md_name, title, depth in make.DOCS:
        assert Path(f"site/{name}.src.html").read_text(encoding="utf-8") == make.doc_page(Path("docs") / md_name, title, name, depth), name
    ref = make.reference()
    for code in ("E01", "E32", "W09"):
        assert f'id="{code}"' in ref


def test_markdown_tables_have_even_rows():
    """表の中の | がエスケープされていないと、行の列数がずれる（GitHub でもホームページでも崩れる）"""
    import glob
    for p in glob.glob("docs/*.md") + ["README.md"]:
        rows = []
        for line in open(p, encoding="utf-8").read().splitlines() + [""]:
            if line.startswith("|"):
                rows.append(len(re.split(r"(?<!\\)\|", line.strip())) - 2)
            elif rows:
                bad = [n for n in rows if n != rows[0]]
                assert not bad, f"{p}: 列数がずれている表があります {rows}"
                rows = []
