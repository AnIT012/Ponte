action ExtractDeadline
  input   mail: Message
  output  deadline: datetime
  example "10/15(木)12:00まで" -> 10/15 12:00
  example "【締切9/24 23:59】" -> 9/24 23:59
  never   guess the year
  else    ask user
  by      ai
  how
    repeat until deadline is found
