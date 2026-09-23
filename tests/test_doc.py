"""ponte doc: 決めごとの1枚。"""
from ponte.cli import main
from ponte.doc import build
from ponte.parser import parse_file


def test_doc_shows_decisions_and_open_items(tmp_path):
    lend = build(parse_file("spec/lend.ponte"))
    assert "備品かしだし" in lend and "誰が何をできるか" in lend and "空いている備品を借りる" in lend
    assert "ここに無いことは、誰にもできません" in lend
    hub = build(parse_file("spec/hub.ponte"))
    assert "timezone" in hub and "AIに任せた所" in hub and "まだ数えていません" in hub
    out = tmp_path / "x.html"
    assert main(["doc", "spec/todo.ponte", "-o", str(out)]) == 0 and "<!doctype html>" in out.read_text(encoding="utf-8")


def test_doc_escapes_text():
    from ponte.parser import parse
    src = open("spec/todo.ponte", encoding="utf-8").read().replace("why    終わったら消えてほしい", "why    <script>x</script>")
    assert "<script>x</script>" not in build(parse(src))
