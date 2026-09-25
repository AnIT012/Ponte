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

rule Remind
  because "締切を落とさないため"
  when deadline within 3 days
  do notify user each of DueSoon
