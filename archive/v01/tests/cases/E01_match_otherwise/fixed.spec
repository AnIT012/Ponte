entity Application
  owner:    ref User
  company:  ref Company
  deadline: datetime
  status:   one of [draft, submitted, passed, failed]

match Application.status to color
  draft     -> red
  submitted -> gray
  passed    -> blue
  otherwise -> gray
