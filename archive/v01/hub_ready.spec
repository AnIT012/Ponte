# 就活Hub「メール→締切→通知」— 渡せる版
# hub.spec から unknown / proposed / ParseApplicationMail(△・example と else が無い) を外したもの。
# unknown の答え（timezone of deadline / who can delete Application）は QUESTIONS.md Q1 で判断待ち。

entity Application
  owner:    ref User
  company:  ref Company
  deadline: datetime
  status:   one of [draft, submitted, passed, failed]

flow Application.status
  draft -> submitted -> passed | failed
  on conflict failed wins over passed

list DueSoon
  from Application
  where status is draft
  where deadline within 3 days
  sort by deadline

match Application.status to color
  draft     -> red
  submitted -> gray
  passed    -> blue
  otherwise -> gray

rule Remind
  because "締切を落とさないため"
  when every day at 21:00
  do notify user each of DueSoon
  example
    given Application(company "Osaka Gas", deadline "9/24 23:59", status draft)
    at "9/21 21:00"
    expect notify "Osaka Gas"

rule MarkSubmitted
  because "ユーザーの一言で提出済みにするため"
  when user says "submitted {company}"
  do move Application where company is {company} to submitted

action ExtractDeadline
  input   mail: Message
  output  deadline: datetime
  example "10/15(木)12:00まで" -> 10/15 12:00
  example "【締切9/24 23:59】" -> 9/24 23:59
  never   guess the year
  else    ask user
  by      ai
  how
    limit 5 seconds
    on failure retry 3 times

connect gmail
  sends new message: Message
