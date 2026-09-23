```lang
do
  text = normalize mail
  found_patterns = find all TimePattern in text
  status[found | notfound | multiple] = match count of found_patterns
                                         1    -> found
                                         0    -> notfound
                                         else -> multiple
  output = match status
            found    -> found monthday of first of found_patterns
            notfound -> missing
            multiple -> missing

shape TimePattern
  month  digits 1..2
  "/"
  day    digits 1..2
  maybe  "(" any 1..5 ")"
  maybe  space
  hour   digits 1..2
  ":"
  minute digits 1..2
```
