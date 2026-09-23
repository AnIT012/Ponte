```
do
  hits   = find all Deadline in mail
  kind[one | none | many] = match count of hits
                              1    -> one
                              0    -> none
                              else -> many
  result = match kind
             one  -> found monthday of first of hits
             none -> missing
             many -> missing

shape Deadline
  month digits 1..2
  "/"
  day   digits 1..2
  maybe "(" any 1..2 ")"
  maybe space
  hour  digits 1..2
  ":"
  minute digits 1..2
```
