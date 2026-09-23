"""フェーズ2：Go変換のテスト。

- 同じ仕様を2回変換したら完全に同じ Go が出る（決定性）
- 生成した Go が go vet / go test を通る（go が無ければスキップ）
- 決まっていない書き方は推測せず CodegenError で止まる
"""
import shutil
import subprocess
from pathlib import Path

import pytest

from lang_v01.codegen import CodegenError, generate, generate_to_dir
from lang_v01.parser import parse, parse_file

HUB = Path("spec/hub_ready.spec")


def test_deterministic():
    a = generate(parse_file(str(HUB)))
    b = generate(parse_file(str(HUB)))
    assert a == b
    # 別のパスに置いた同じ内容でも同じ
    c = generate(parse(HUB.read_text(encoding="utf-8"), path="other.spec"))
    assert a == c


def test_committed_output_is_up_to_date():
    """generated/hub は spec/hub_ready.spec からの変換結果と一致する。"""
    files = generate(parse_file(str(HUB)))
    for name, content in files.items():
        p = Path("generated/hub") / name
        assert p.exists(), f"{p} がありません（python -m lang gen spec/hub_ready.spec -o generated/hub）"
        assert p.read_text(encoding="utf-8") == content, f"{p} が古い"


@pytest.mark.skipif(shutil.which("go") is None, reason="go が無い")
def test_generated_go_builds_and_passes(tmp_path):
    generate_to_dir(parse_file(str(HUB)), str(tmp_path))
    shutil.copy("tests/v01/go/semantics_test.go", tmp_path / "semantics_test.go")
    for cmd in (["gofmt", "-l", "."], ["go", "vet", "./..."], ["go", "test", "-race", "./..."]):
        r = subprocess.run(cmd, cwd=tmp_path, capture_output=True, text=True)
        assert r.returncode == 0, f"{' '.join(cmd)}\n{r.stdout}\n{r.stderr}"
        if cmd[0] == "gofmt":
            assert r.stdout.strip() == "", f"gofmt が直したいファイルがある: {r.stdout}"


@pytest.mark.parametrize("text, msg", [
    ("entity A\n  x: text\n\nlist L\n  from A\n  where x seems related\n", "where の書き方"),
    ("entity A\n  x: text\n\nrule R\n  when user does click\n  do send mail\n", "do の書き方"),
    ("entity A\n  s: one of [a, b]\n\nrule R\n  when user does click\n  do move A where s is a to b\n", "flow がありません"),
    ("entity A\n  x: text\n\nlist L\n  from A\n  where x within 3 days\n", "datetime の項目"),
])
def test_undecided_forms_stop(text, msg):
    with pytest.raises(CodegenError) as e:
        generate(parse(text))
    assert msg in str(e.value)


BY_SPEC = """entity A
  x: text

connect gmail
  sends new message: Message

action ByCode
  input  m: Message
  output r: text
  example "a" -> "b"
  example "c" -> "d"
  else   skip
  by     code "mine.go"

action ByConnect
  input  m: Message
  output r: text
  example "a" -> "b"
  example "c" -> "d"
  else   skip
  by     connect gmail
"""


@pytest.mark.skipif(shutil.which("go") is None, reason="go が無い")
def test_by_code_and_by_connect_skeleton(tmp_path):
    files = generate(parse(BY_SPEC))
    assert "GmailConnector" in files["connects.go"] and "OnNewMessage" in files["connects.go"]
    assert 'by code "mine.go"' in files["actions.go"]
    assert "ByConnectByGmail" in files["actions.go"]
    generate_to_dir(parse(BY_SPEC), str(tmp_path))
    r = subprocess.run(["go", "vet", "./..."], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_by_connect_without_connect_stops():
    with pytest.raises(CodegenError) as e:
        generate(parse(BY_SPEC.replace("connect gmail\n  sends new message: Message\n\n", "")))
    assert "connect がありません" in str(e.value)
