"""エラーの辞書（ponte/errors.py）が checker と仕様書とずれていないか。"""
import glob
import json
import re

from ponte.cli import main
from ponte.errors import BY_CODE, explain
from ponte.guide import errors_block


def test_every_code_the_checker_emits_is_explained():
    src = "".join(open(p, encoding="utf-8").read() for p in glob.glob("ponte/*.py"))
    emitted = set(re.findall(r'Finding\("([EW]\d+)"', src)) | {"E26", "W26"}
    assert emitted - set(BY_CODE) == set()


def test_spec_chapter_13_is_generated():
    assert errors_block() in open("docs/言語仕様_v0.3.md", encoding="utf-8").read()


def test_explain_command(capsys):
    assert main(["explain", "e05"]) == 0
    assert "tbd" in capsys.readouterr().out
    assert explain("E99") is None
    assert main(["explain", "E99"]) == 1


def test_check_json(capsys):
    assert main(["check", "--json", "tests/cases/E32_unknown_state/broken.ponte"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["findings"][0]["code"] == "E32"
    assert main(["check", "--json", "tests/cases/E32_unknown_state/fixed.ponte"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_version_matches_pyproject():
    import re as _re
    from ponte import __version__
    assert _re.search(r'version = "([^"]+)"', open("pyproject.toml", encoding="utf-8").read()).group(1) == __version__
