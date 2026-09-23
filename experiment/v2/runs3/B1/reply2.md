```lang
do
  clean = normalize mail
  hits = find all Deadline in clean
  count_hits[one | many | none] = match count of hits
                                    1 -> one
                                    0 -> none
                                    else -> many
  result = match count_hits
             one -> found monthday of first of hits
             else -> missing

shape Deadline
  month     digits 1..2
  "/"
  day       digits 1..2
  maybe     "(" any 1 ")"
  maybe     space
  hour      digits 1..2
  ":"
  minute    digits 1..2
```
