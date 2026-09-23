import pytest

from ponte.cli import main
from ponte.parser import ParseError, flow_parts, parse, parse_file, relate_lines, states_of, thing_fields


def test_tree_and_fields():
    spec = parse_file("spec/hub_ready.ponte")
    app = spec.find("thing", "Application")
    fields = {f.name: f for f in thing_fields(app)}
    assert fields["status"].states == ["draft", "submitted", "passed", "failed"]
    assert fields["owner"].type == "User" and fields["owner"].gone == "remove too"
    flow = spec.find("flow", "Application.status")
    assert flow_parts(flow) == ([("draft", "submitted"), ("submitted", "passed"), ("submitted", "failed")], [("failed", "passed")])


def test_comments():
    spec = parse('list L\n  of A\n  ## where x is y   # 理由\n  where s is a   ## 本当？\n  where t is "a # b"\n')
    assert spec.blocking == [(3, "where x is y   # 理由")]
    lst = spec.find("list", "L")
    assert lst.children_of("where")[0].blocking == "本当？"
    assert lst.children_of("where")[1].text == 't is "a # b"'


def test_group_members_are_declarations():
    spec = parse("group Mail\n  rule A\n    when user says \"x\"\n  relate\n    A then B\n")
    assert [d.keyword for d in spec.decls()] == ["group", "rule", "relate"]
    assert relate_lines(spec) == [("A", "then", "B", 5)]


def test_states_of():
    assert states_of("[a | b | c] = match x") == ["a", "b", "c"]
    assert states_of("text") is None


def test_errors_have_line_numbers():
    with pytest.raises(ParseError) as e:
        parse("thing A\n  x text\n    y text\n foo text\n")
    assert e.value.line == 4
    with pytest.raises(ParseError) as e:
        parse("hello\n")
    assert e.value.line == 1
    with pytest.raises(ParseError) as e:
        parse("thing A\n\tx text\n")
    assert e.value.line == 2


def test_cli(capsys, tmp_path):
    assert main(["check", "spec/hub.ponte"]) == 1
    assert "渡せません（1件）" in capsys.readouterr().out
    assert main(["check", "spec/hub_ready.ponte"]) == 0
    assert "AIに渡せます" in capsys.readouterr().out
    # 形を残して、次に thing を変えたら change を求められる
    p = tmp_path / "a.ponte"
    src = open("spec/hub_ready.ponte", encoding="utf-8").read()
    p.write_text(src, encoding="utf-8")
    assert main(["check", str(p), "--save-shape"]) == 0
    p.write_text(src.replace("  deadline  monthday\n", "  deadline  monthday\n  memo      text\n"), encoding="utf-8")
    assert main(["check", str(p)]) == 1
    assert "change がありません" in capsys.readouterr().out
