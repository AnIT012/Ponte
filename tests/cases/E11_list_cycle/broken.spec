entity Application
  owner:    ref User
  company:  ref Company
  deadline: datetime
  status:   one of [draft, submitted, passed, failed]

list DueSoon
  from Urgent
  where status is draft

list Urgent
  from DueSoon
  where deadline within 1 days
