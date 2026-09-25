entity Application
  owner:    ref User
  company:  ref Company
  deadline: datetime
  status:   one of [draft, submitted, passed, failed]

flow Application.status
  draft -> submitted -> passed | failed
  on conflict failed wins over passed

rule OnSubmitted
  when Application moves to submitted
  do notify user "提出しました"

rule OnPassed
  when Application moves to passed
  do notify user "通過しました"
