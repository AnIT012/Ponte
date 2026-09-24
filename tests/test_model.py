"""model（仕様 5章）: 約束（learn / using / require / else / example）を Ponte の側で守らせる。"""
import csv
import os
import shutil

import pytest

from ponte.checker import check
from ponte.examples import holes, run_examples
from ponte.model import decls, encoder, fingerprint, load, predict, save, train, verdict
from ponte.nn import MLP
from ponte.parser import parse, parse_file
from ponte.runtime import Ctx, Engine

ROWS = list(csv.DictReader(open("spec/churn.csv", encoding="utf-8")))


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    d = tmp_path_factory.mktemp("churn")
    p = d / "churn.ponte"
    shutil.copy("spec/churn.ponte", p)
    spec = parse_file(str(p))
    m = decls(spec)["Churn"]
    t = train(spec, m, ROWS)
    save(spec, t)
    return p, t


def codes(src):
    return [f.code for f in check(parse(src)) if f.is_error]


BASE = open("spec/churn.ponte", encoding="utf-8").read().split("model Churn")[0]


def model(body):
    return BASE + "model Churn\n" + body + "\nlist AtRisk\n  of     Customer\n  where  predict Churn for it is yes\n"


GOOD = "  learn    will_leave from Customer\n  using    visits, months\n  require  accuracy at least 80%\n  else     skip\n"


def test_nn_learns_xor():
    m = MLP([2, 8, 2], seed=1)
    m.fit([[0, 0], [0, 1], [1, 0], [1, 1]] * 20, [0, 1, 1, 0] * 20, epochs=300, lr=0.05, batch=8)
    assert [round(m.predict_proba(x)[1]) for x in ([0, 0], [0, 1], [1, 0], [1, 1])] == [0, 1, 1, 0]


def test_sample_spec_passes_check():
    assert [f for f in check(parse_file("spec/churn.ponte")) if f.is_error] == []


@pytest.mark.parametrize("body,code", [
    (GOOD.replace("  require  accuracy at least 80%\n", ""), "E28"),               # 合格の条件を決めていない
    (GOOD.replace("  else     skip\n", ""), "E04"),                                 # 使えないときを決めていない
    (GOOD.replace("will_leave from", "name from"), "E32"),                          # 状態でない項目は当てられない
    (GOOD.replace("visits, months", "visits, name"), "E32"),                        # text は見せられない
    (GOOD.replace("visits, months", "visits, will_leave"), "E32"),                  # 答えを入力にしない
    (GOOD.replace("visits, months", "visits, mnths"), "E32"),                       # 打ち間違い
    (GOOD + "  example  spend 0 -> yes\n", "E32"),                                  # using にない項目の例
    (GOOD + "  example  visits 0 -> maybe\n", "E32"),                               # ない状態の例
    (GOOD.replace("accuracy at least 80%", "accuracy 80"), "E31"),
    (GOOD.replace("else     skip", "else     use default maybe"), "E32"),
])
def test_contract_is_checked_before_running(body, code):
    assert code in codes(model(body))


def test_predict_is_checked():
    assert "E32" in codes(model(GOOD).replace("predict Churn for it is yes", "predict Churn for it is maybe"))
    assert "E28" in codes(model(GOOD).replace("predict Churn for it", "predict Chrn for it"))


def test_untrained_model_is_listed_not_failed(tmp_path):
    p = tmp_path / "c.ponte"
    shutil.copy("spec/churn.ponte", p)
    s = parse_file(str(p))
    assert all(r.ok for r in run_examples(s))
    assert any("まだ学習していません" in h.message for h in holes(s, run_examples(s)))


def test_trained_model_meets_its_contract(trained):
    p, t = trained
    s = parse_file(str(p))
    assert t["accuracy"] >= 0.8 and t["held_back"] == len(ROWS) // 5
    assert verdict(s, decls(s)["Churn"], load(s, "Churn"))[0]
    assert all(r.ok for r in run_examples(s))


def test_below_require_fails_test_and_falls_back_to_else(trained, tmp_path):
    p, _ = trained
    for other, expect_at_risk in (("else     skip", 0), ("else     use default yes", 20)):
        q = tmp_path / f"strict{expect_at_risk}.ponte"
        q.write_text(p.read_text(encoding="utf-8").replace("at least 80%", "at least 99%").replace("else     skip", other),
                     encoding="utf-8")
        shutil.copytree(str(p) + ".models", str(q) + ".models")
        s = parse_file(str(q))
        assert not all(r.ok for r in run_examples(s))                               # ponte test が落ちる
        eng = Engine(s)
        me = eng.login("me")
        for r in ROWS[:20]:
            eng.create("Customer", dict(r), me, fire=False, check=False)
        assert not eng.trained and len(eng.list_items("AtRisk", Ctx(me))) == expect_at_risk


def test_changed_definition_needs_training_again(trained, tmp_path):
    p, t = trained
    q = tmp_path / "changed.ponte"
    q.write_text(p.read_text(encoding="utf-8").replace("using    visits, spend, months, plan", "using    visits, months, plan")
                 .replace("visits 0, spend 0, months 1", "visits 0, months 1").replace("visits 20, spend 30000, months 36", "visits 20, months 36"),
                 encoding="utf-8")
    shutil.copytree(str(p) + ".models", str(q) + ".models")
    s = parse_file(str(q))
    ok, why = verdict(s, decls(s)["Churn"], load(s, "Churn"))
    assert not ok and "定義が違います" in why[0]


def test_model_sees_only_using_fields(trained):
    _, t = trained
    row = dict(ROWS[0])
    assert predict(t, row) == predict(t, {**row, "name": "別の名前", "will_leave": "no" if row["will_leave"] == "yes" else "yes"})
    assert [e["field"] for e in t["encoder"]] == ["visits", "spend", "months", "plan"]


def test_training_is_reproducible(trained):
    p, t = trained
    s = parse_file(str(p))
    again = train(s, decls(s)["Churn"], ROWS)
    assert again["net"] == t["net"] and again["accuracy"] == t["accuracy"]


def test_too_few_records_is_an_error():
    s = parse_file("spec/churn.ponte")
    with pytest.raises(ValueError):
        train(s, decls(s)["Churn"], ROWS[:10])
