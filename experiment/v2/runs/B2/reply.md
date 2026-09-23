```lang
action ExtractDeadline
  in      mail text
  out     found monthday | missing
  example "10/15(木)12:00まで"            -> found 10/15 12:00
  example "【締切9/24 23:59】"            -> found 9/24 23:59
  example "来週中にご提出ください"        -> missing
  example "9/24 23:59 または 9/30 23:59"  -> missing
  never   guess the year
  else    ask user
  by      ai

do
  clean = normalize mail
  hits  = find all Deadline in clean
  kind[one | none | many] = match count of hits
                              1    -> one
                              0    -> none
                              else -> many
  deadline = match kind
               one  -> found monthday of first of hits
               none -> missing
               many -> missing

shape Deadline
  month digits 1..2
  "/"
  day digits 1..2
  maybe "(" any 1 ")"
  maybe space
  maybe hour digits 1..2 ":" minute digits 1..2
```
