"""rule の書き方の一覧。ここが元で、チェッカー・AIへの説明（ponte guide --rules）を、ここから作る。
1つずつ「書き方・意味・例」を持つ（tests/test_guide.py が、例がチェッカーを通るか確かめる）。"""
from __future__ import annotations

# when に書ける出来事: (正規表現, 書き方, 意味, 例, 実行エンジンが起こすか)
WHEN_FORMS = [
    (r"every (day|monday|tuesday|wednesday|thursday|friday|saturday|sunday) at \d{1,2}:\d{2}",
     "every day at 21:00 / every monday at 9:00", "毎日・毎週その時刻に", "every day at 21:00", True),
    (r"every month on (\d{1,2}|last) at \d{1,2}:\d{2}", "every month on 1 at 9:00 / every month on last at 18:00",
     "毎月その日のその時刻に（last は月末。31 のように無い日の月は月末に）", "every month on 1 at 9:00", True),
    (r"at \S.*", "at 9/24 23:00", "その日時に1回", "at 9/24 23:00", True),
    (r'user says ".*"', 'user says "submitted {company}"', "人が言った（{…} は変数になる）", 'user says "submitted {company}"', True),
    (r"user taps \S+ on \S+", "user taps 名前 on 画面か thing", "ボタンを押した（押された1件が this）", "user taps borrow-button on Item", True),
    (r"[A-Z][\w.]* is created", "Loan is created", "箱ができた（this はその箱）", "Loan is created", True),
    (r"[A-Z][\w.]* moves to \w+", "Loan moves to returned", "状態が動いた", "Loan moves to returned", True),
    (r"[A-Z][\w.]* is removed", "Loan is removed", "箱が消えた", "Loan is removed", True),
    (r"[A-Z]\w* gives \S.*", "Gmail gives new message", "connect の gives が届いた（入力は届いた中身）", "Gmail gives new message", True),
    # 書き方は決まっているが、今の実行エンジンはまだ起こさない（check でエラーにする）
    (r"user holds \S.*", "user holds 名前", "長押し", "user holds card", False),
    (r"user swipes \S+ (left|right|up|down)", "user swipes 名前 left", "スワイプ", "user swipes card left", False),
    (r"user drags \S+ to \S+", "user drags 名前 to 名前", "ドラッグ（board の列の移動は move として起きる）", "user drags card to done", False),
    (r"user types in \S+", "user types in 名前", "入力中", "user types in search", False),
    (r"user (opens|leaves) \w+", "user opens 画面 / user leaves 画面", "画面を開いた / 離れた", "user opens Home", False),
]

# do に書ける形: (正規表現, 書き方, 意味, 例)
DO_FORMS = [
    (r'notify \w+ ".*"', 'notify me "..." / notify borrower "..."', "通知する（宛先は me か、人を指す項目。{項目} は中身に）", 'notify borrower "{item} の返却日です"'),
    (r"notify \w+ each of \w+", "notify owner each of DueSoon", "一覧のそれぞれを、その箱の人へ", "notify owner each of DueSoon"),
    (r"move this to \w+", "move this to 状態", "押された1件の状態を動かす（flow の矢印だけ）", "move this to returned"),
    (r"move \w+ of this to \w+", "move 項目 of this to 状態", "this が指している箱を動かす", "move item of this to lent"),
    (r"move \w+ where .+ to \w+", "move 箱 where 条件 to 状態", "絞った箱を全部動かす", "move Loan where due is before now to late"),
    (r"remove this", "remove this", "押された1件を消す（gone の通り）", "remove this"),
    (r"go \w+( with this)?", "go 画面 / go 画面 with this", "画面を移る", "go Detail with this"),
    (r"create \w+", "create 箱（下に「項目 値」）", "箱を作る", "create Loan"),
    (r"set \w+ to .+", "set 項目 to 値", "項目を書き換える（状態は move で）", "set yen to result"),
    (r"(\w+) with (\w+)", "action名 with 項目", "action を呼ぶ。入力は this の項目", "FindYen with memo"),
]

# create の「項目 値」と set の値: (正規表現, 書き方, 意味)
VALUE_FORMS = [
    (r"this", "this", "押された1件"),
    (r"me", "me", "押した人"),
    (r"result", "result", "直前の action の答え（relate の then で渡る。答えが無ければ、この rule は静かに起きない）"),
    (r"\w+ of this", "項目 of this", "this の項目の値"),
    (r'".*"', '"文字"', "そのままの値"),
    (r"\{\w+\}", "{名前}", "when の {…} で取り出した値"),
    (r"\d+ (minutes?|hours?|days?|weeks?) from now", "7 days from now", "今から（年まで入れて保存。推測しない）"),
    (r"[\w/:. -]+", "状態の名前・数", "そのまま"),
]
