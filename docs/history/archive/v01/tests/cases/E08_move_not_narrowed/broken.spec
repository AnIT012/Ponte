entity Application
  owner:    ref User
  company:  ref Company
  deadline: datetime
  status:   one of [draft, submitted, passed, failed]

flow Application.status
  draft -> submitted -> passed | failed
  on conflict failed wins over passed

rule MarkSubmitted
  when user says "submitted {company}"
  do move Application to submitted
