```lang
do
  normalized = normalize mail
  matches = find all Deadline in normalized
  count[one | none | many] = match count of matches
                               1    -> one
                               0    -> none
                               else -> many
  answer = match count
             one  -> found monthday of first of matches
             none -> missing
             many -> missing

shape Deadline
  month  digits 1..2
  "/"
  day    digits 1..2
  maybe  "(" any 1..5 ")"
  maybe  space
  hour   digits 1..2
  ":"
  minute digits 1..2
```
