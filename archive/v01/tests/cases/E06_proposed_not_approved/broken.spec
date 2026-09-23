entity Application
  owner:    ref User
  company:  ref Company
  deadline: datetime
  status:   one of [draft, submitted, passed, failed]

never notify for status failed   # proposed by ai
