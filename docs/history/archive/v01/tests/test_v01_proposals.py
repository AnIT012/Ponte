from lang_v01.cli import main
from lang_v01.parser import parse
from lang_v01.proposals import list_proposals


def test_list_proposals():
    spec = parse("entity A\n  x: text\n\nnever notify for status failed   # proposed by ai\nnever delete A\n")
    items = list_proposals(spec)
    assert len(items) == 1 and items[0].line == 4 and "proposed by ai" in items[0].by


def test_cli_exit_codes(capsys):
    assert main(["proposals", "spec/hub.spec"]) == 1
    assert "承認待ち（1件）" in capsys.readouterr().out
    assert main(["proposals", "spec/hub_ready.spec"]) == 0
    assert main(["check", "spec/hub.spec"]) == 1
    assert main(["check", "spec/hub_ready.spec"]) == 0
