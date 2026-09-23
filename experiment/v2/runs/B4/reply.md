```
do
  clean  = normalize mail
  hits   = find all Deadline in clean
  kind[one | zero | many] = match count of hits
                              1    -> one
                              0    -> zero
                              else -> many
  result = match kind
             one  -> found monthday of first of hits
             zero -> missing
             many -> missing

shape Deadline
  month digits 1..2
  "/"
  day   digits 1..2
  maybe "(" any 1..2 ")"
  maybe space
  hour   digits 1..2
  ":"
  minute digits 1..2
```
