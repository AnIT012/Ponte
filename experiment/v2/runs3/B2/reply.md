```lang
do
  clean = normalize mail
  deadlines = find all DatetimePattern in clean
  numDeadlines[single | empty | multiple] = match count of deadlines
                                              1    -> single
                                              0    -> empty
                                              else -> multiple
  result = match numDeadlines
             single   -> found monthday of first of deadlines
             empty    -> missing
             multiple -> missing

shape DatetimePattern
  m    digits 1..2
  "/"
  d    digits 1..2
  maybe "(" any 1..5 ")"
  maybe space
  h    digits 1..2
  ":"
  min  digits 1..2
```
