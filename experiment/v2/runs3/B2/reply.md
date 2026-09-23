```lang
do
  clean = normalize mail
  dates = find all Deadline in clean
  count_dates = count of dates
  kind[one | none | many] = match count_dates
                              1    -> one
                              0    -> none
                              else -> many
  result = match kind
             one  -> found monthday of first of dates
             none -> missing
             many -> missing

shape Deadline
  month digits 1..2
  "/"
  day digits 1..2
  maybe space
  maybe hour digits 1..2
  maybe ":"
  maybe minute digits 1..2
```
