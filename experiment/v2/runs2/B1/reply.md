```
do
  clean = normalize mail
  hits  = find all Deadline in clean
  kind[one | many] = match count of hits
                        1    -> one
                        else -> many
  result = match kind
             one  -> found monthday of first of hits
             many -> missing

shape Deadline
  month digits 1..2
  "/"
  day digits 1..2
  maybe "(" any 1..2 ")"
  maybe space
  hour digits 1..2
  ":"
  minute digits 1..2
```
