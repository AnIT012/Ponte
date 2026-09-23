```lang
do
  clean = normalize mail
  hits = find all Deadline in clean
  kind[one | none | many] = match count of hits
                             1 -> one
                             0 -> none
                             else -> many
  deadline = match kind
             one -> found monthday of first of hits
             else -> missing

shape Deadline
  month digits 1..2
  "/"
  day digits 1..2
  maybe space
  maybe "(" any 1 ")"
  maybe space
  hour digits 1..2
  ":"
  minute digits 1..2
```
