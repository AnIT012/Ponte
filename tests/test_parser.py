import pytest

from lang.parser import ParseError, entity_fields, flow_conflicts, flow_states, flow_transitions, parse, parse_file


def test_tree_shape():
    spec = parse_file("spec/hub_ready.spec")
    kinds = [d.keyword for d in spec.decls]
    assert kinds == ["entity", "flow", "list", "match", "rule", "rule", "action", "connect"]
    rule = spec.find("rule", "Remind")
    ex = rule.child("example")
    assert [c.keyword for c in ex.children] == ["given", "at", "expect"]
    assert rule.line == 27


def test_entity_fields_and_flow():
    spec = parse_file("spec/hub_ready.spec")
    ent = spec.find("entity", "Application")
    assert [f[0] for f in entity_fields(ent)] == ["owner", "company", "deadline", "status"]
    flow = spec.decls_of("flow")[0]
    assert flow_transitions(flow) == [("draft", "submitted"), ("submitted", "passed"), ("submitted", "failed")]
    assert flow_states(flow) == ["draft", "submitted", "passed", "failed"]
    assert flow_conflicts(flow) == [("failed", "passed")]


def test_comment_and_proposed():
    spec = parse("never notify for status failed   # proposed by ai\n")
    n = spec.decls[0]
    assert n.proposed and n.text == "notify for status failed"
    spec = parse('rule A\n  when user says "say # not comment"\n')
    assert spec.decls[0].child("when").text == 'user says "say # not comment"'


def test_two_word_clauses():
    spec = parse("list L\n  from A\n  sort by deadline\n")
    assert spec.decls[0].child("sort by").text == "deadline"


def test_errors_have_line_numbers():
    with pytest.raises(ParseError) as e:
        parse("entity A\n  x: text\n\n  broken indent\n foo: text\n")
    assert e.value.line == 5
    with pytest.raises(ParseError) as e:
        parse("hello world\n")
    assert e.value.line == 1
    with pytest.raises(ParseError) as e:
        parse("entity A\n\tx: text\n")
    assert e.value.line == 2
