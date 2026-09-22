entity Application
  owner:    ref User
  company:  ref Company
  deadline: datetime
  status:   one of [draft, submitted, passed, failed]

list DueSoon
  from Application
  where status is draft
  where deadline within 3 days
  sort by deadline
