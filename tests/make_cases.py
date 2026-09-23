"""tests/cases/ を作り直す。spec/hub_ready.lang を土台に、エラーごとに壊した／直した仕様を作る。

  python tests/make_cases.py
"""
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lang.checker import shape_of  # noqa: E402
from lang.parser import parse  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
base = open(os.path.join(ROOT, "spec/hub_ready.lang"), encoding="utf-8").read()


def rep(old, new, s=None):
    """old を探して new に置き換える。空白の数の違い（整形のゆれ）は気にしない"""
    s = base if s is None else s
    pat = re.sub(r"(?: )+", lambda m: " +" if len(m.group(0)) > 1 or True else " ", re.escape(old).replace("\\ ", " "))
    m = re.search(pat, s)
    assert m, old
    lead_old = len(old) - len(old.lstrip(" "))
    if lead_old:                                     # 置き換える行の字下げは、見つけた行の字下げに合わせる
        lead_found = len(m.group(0)) - len(m.group(0).lstrip(" "))
        new = "\n".join((" " * (lead_found - lead_old) + l) if l.strip() and lead_found > lead_old
                         else (l[lead_old - lead_found:] if l.strip() and lead_found < lead_old else l)
                         for l in new.split("\n"))
    return s[:m.start()] + new + s[m.end():]


act_by = "  by      ai\n"
cases = {}
cases["E01_match_else"] = (rep("  failed    -> gray\n", ""), base)
cases["E02_until_limit"] = (rep(act_by, act_by + "  how\n    repeat check until found\n"), rep(act_by, act_by + "  how\n    repeat check until found or 3 times\n"))
three = '  example "【締切9/24 23:59】"            -> found 9/24 23:59\n  example "来週中にご提出ください"        -> missing\n  example "9/24 23:59 または 9/30 23:59"  -> missing\n'
cases["E03_action_examples"] = (rep(three, ""), base)
cases["E04_action_else"] = (rep("  else    ask user\n", ""), base)
cases["E05_tbd"] = (base + "\ntbd\n  timezone of deadline\n", base)
cases["E06_blocking_line"] = (rep("  sort  deadline\n", "  sort  deadline\n  ## where deadline is after now    # 締切が過ぎた応募も通知する？\n"), base)
cases["E06_blocking_inline"] = (rep("  where status is draft\n", "  where status is draft    ## draft だけでいい？\n"), base)
cases["E07_when_is_state"] = (rep("  when  every day at 21:00\n", "  when  deadline within 3 days\n"), base)
cases["E08_move_narrowed"] = (rep("  do    move this to submitted\n", "  do    move Application to submitted\n"), rep("  do    move this to submitted\n", '  do    move Application where company is "x" to submitted\n'))
cov = base + '\nrule OnSubmitted\n  when  Application moves to submitted\n  do    notify owner "提出しました"\n\nrule OnPassed\n  when  Application moves to passed\n  do    notify owner "通過しました"\n'
cases["W09_flow_coverage"] = (cov, cov + '\nrule OnFailed\n  when  Application moves to failed\n  do    notify owner "残念でした"\n')
cases["E10_conflict"] = (rep("  failed > passed\n", ""), base)
cases["E11_list_cycle"] = (base + "\nlist A\n  of    B\n  where status is draft\n\nlist B\n  of    A\n  where status is draft\n",
                           base + "\nlist A\n  of    Application\n  where status is draft\n\nlist B\n  of    A\n  where status is draft\n")
old_given = base.replace("    given   Application\n      company   \"Osaka Gas\"\n      deadline  \"9/24 23:59\"\n      status    draft\n", "    given   Application(company \"Osaka Gas\", deadline \"9/24 23:59\", status draft)\n")
assert old_given != base
cases["E12_example_parentheses"] = (old_given, base)
cases["E12_part_calc_outside_do"] = (base + "\npart Badge\n  in    deadline monthday\n  left = days until deadline\n  show  text \"{left}\"\n",
                                     base + "\npart Badge\n  in    deadline monthday\n  do\n    left = days until deadline\n  show  text \"{left}\"\n")
cases["E12_nesting_and"] = (rep("  where status is draft\n  where deadline within 3 days\n", "  where status is draft and deadline within 3 days\n"), base)
cases["E12_nesting_do_where"] = (rep("  do    move this to submitted\n", "  do    move this to submitted\n    where company is \"x\"\n"), base)
cases["E12_nesting_match_in_match"] = (rep("            else -> DueSoon as cards\n", "            else -> match count of Application\n"), base)
cases["E13_contract"] = (rep("  out     found monthday | missing\n", "  out     found date | missing\n"), base)
cases["E14_relate_cycle"] = (base + "\nrelate\n  Remind        then MarkSubmitted\n  MarkSubmitted then Remind\n", base + "\nrelate\n  Remind        then MarkSubmitted\n")
cases["E15_relate_contradiction"] = (base + "\nrelate\n  Remind > MarkSubmitted\n", base)
cases["E16_before_impossible"] = (base + "\nrelate\n  Ghost before Remind\n", base + "\nrelate\n  ReadMail before Remind\n")
cases["E17_double_else"] = (base + "\nrelate\n  ExtractDeadline else Remind\n", rep("  else    ask user\n", "") + "\nrelate\n  ExtractDeadline else Remind\n")
cases["E18_match_state"] = (rep("  failed    -> gray\n", "  faild     -> gray\n"), base)
do_ = act_by + "  do\n    hits = find all Deadline in mail\n    kind[one | many] = match count of hits\n                         1    -> one\n                         else -> {}\n"
cases["E18_local_state"] = (rep(act_by, do_.format("mnay")), rep(act_by, do_.format("many")))
cases["E19_who"] = (rep("  user   can see    User where it is me\n", ""), base)
cases["E20_gone_missing"] = (rep(" gone[remove too]", ""), base)
cases["E20_gone_choice"] = (rep("gone[remove too]", "gone[delete]"), base)
cases["E21_change_init"] = (base + '\nchange Application to v2\n  add memo text\n', base + '\nchange Application to v2\n  add memo text = ""\n')
SHAPE = "E21_shape_changed"
cases[SHAPE] = (rep("  deadline  monthday\n", "  deadline  monthday\n  memo      text\n"),
                rep("  deadline  monthday\n", "  deadline  monthday\n  memo      text\n") + '\nchange Application to v2\n  add memo text = ""\n')
ask = '\naction Classify\n  in      mail text\n  out     passed | failed | unknown\n  example "選考通過のお知らせ" -> passed\n  example "今回はご縁がなく" -> failed\n  else    skip\n  ask     ai\n'
cases["E22_ask_ai_limit"] = (base + ask, base + ask + "  how\n    limit 5 seconds\n")
conn = rep("  gives  new message  Message\n", "  gives  new message  Message\n  does   send mail    to text, body text -> sent | failed\n")
send = conn + '\nrule SendDigest\n  when  every day at 8:00\n  do    Gmail send mail to "me", body "今日の締切"\n'
cases["E23_connect_fallback"] = (send, send + "\nrelate\n  SendDigest else Remind\n")
det = base + "\nscene Detail\n  main  DueSoon as detail\n\nrule OpenDetail\n  when  user taps card on DueSoon\n  do    go Detail with this\n"
cases["E24_scene_move"] = (det, det.replace("  Home -> AddApplication\n", "  Home -> AddApplication\n  Home -> Detail\n"))
from lang.checker import ui_texts  # noqa: E402
_texts = sorted({t for t, _ in ui_texts(parse(base))})


def words_block(lang, drop=None):
    lines = [f'  "{t}"  {t if lang == "ja" else "EN:" + t}' for t in _texts if t != drop]
    return f"\nwords {lang}\n" + "\n".join(lines) + "\n"


cases["E25_words"] = (base + words_block("ja") + words_block("en", drop=_texts[0]), base + words_block("ja") + words_block("en"))
nb = rep("  button  submitted-button named 提出した\n", "  button  submitted-button\n")
cases["E26_a11y_publish"] = (nb, base)
cases["W26_a11y_draft"] = (nb, base)
money = "\nthing Plan\n  price  money yen\n  fee    money {}\n\nwho\n  user can see Plan\n\naction Total\n  in      plan Plan\n  out     total money yen\n  example \"a\" -> 1\n  example \"b\" -> 2\n  else    skip\n  by      ai\n  do\n    total = price + fee\n"
cases["E27_money"] = (base + money.format("usd"), base + money.format("yen"))
cases["E28_undefined_part"] = (rep("  top     Header\n", "  top     Heder\n"), base)
cases["E28_undefined_list"] = (rep("  side    ", "  side    ") if False else rep("  bottom  button add named 追加\n", "  side    Mine as list\n  bottom  button add named 追加\n"),
                               rep("  bottom  button add named 追加\n", "  side    Mine as list\n  bottom  button add named 追加\n") + "\nlist Mine\n  of    Application\n  sort  deadline\n")
cases["E28_undefined_relate"] = (base + "\nrelate\n  Remind > Remindd\n", base)
cases["E28_unknown_icon"] = (rep("  button  submitted-button named 提出した\n", "  button  submitted-button named 提出した icon sendd\n"),
                             rep("  button  submitted-button named 提出した\n", "  button  submitted-button named 提出した icon send\n"))
cases["E28_unknown_type"] = (rep("  owner     User   gone[remove too]\n", "  owner     Usr    gone[remove too]\n"), base)
cases["E29_two_dos"] = (rep("  do    move this to submitted\n", "  do    move this to submitted\n  do    notify me \"提出しました\"\n"), base)
cases["E30_notify_recipient"] = (rep("notify owner each of DueSoon", "notify each of DueSoon"), base)
cases["E30_notify_unknown_recipient"] = (rep("notify owner each of DueSoon", "notify boss each of DueSoon"), base)
cases["E28_tone_in_style"] = (base + "\nstyle DueSoon\n  submitted-button  tone good\n",
                              rep("  button  submitted-button named 提出した\n", "  button  submitted-button named 提出した tone good\n"))
cases["E28_unknown_field"] = (rep("  title   company\n", "  title   compny\n"), base)
cases["E28_bad_button"] = (rep("  button  submitted-button named 提出した\n", "  button  submitted-button named 提出した blink\n"), base)
cases["E25_words_ui_text_missing"] = (base + "\nwords ja\n  draft  下書き\n\nwords en\n  draft  Draft\n", base + words_block("ja") + words_block("en"))

if __name__ == "__main__":
    out = os.path.join(ROOT, "tests/cases")
    shutil.rmtree(out, ignore_errors=True)
    for name, (bad, ok) in cases.items():
        d = os.path.join(out, name)
        os.makedirs(d)
        open(os.path.join(d, "broken.lang"), "w", encoding="utf-8").write(bad)
        open(os.path.join(d, "fixed.lang"), "w", encoding="utf-8").write(ok)
        if name.startswith("E26"):
            open(os.path.join(d, "publish"), "w").close()
        if name == SHAPE:
            with open(os.path.join(d, "prev.shape.json"), "w", encoding="utf-8") as f:
                json.dump(shape_of(parse(base)), f, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"{len(cases)} 組を作りました")
