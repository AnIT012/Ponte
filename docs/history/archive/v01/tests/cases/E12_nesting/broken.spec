entity Application
  owner:    ref User
  company:  ref Company
  deadline: datetime
  status:   one of [draft, submitted, passed, failed]

rule Remind
  because "締切を落とさないため"
  when every day at 21:00
  do notify user each of Application
    where status is draft
