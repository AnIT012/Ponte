## 共通の指示（A・B 両方に同じものを付ける）

Go 1.22 で `package hub` を1ファイルで書いてください。外部ライブラリは使わないでください。
出力は ```go のコードブロック1つだけにしてください。説明は不要です。

要件に書いていないことや矛盾があって決められない場合は、**コードを書かずに質問だけ**を返してください
（質問は「Q:」で始まる行に1つずつ）。推測で埋めないでください。

テストは次の窓口から行います。この型と関数名・シグネチャは必ずこの通りにしてください。

```go
package hub

// App は応募1件。Deadline は "9/24 23:59" のような "月/日 時:分" の文字列（年は無い）。
type App struct {
	Company  string
	Deadline string
	Status   string // draft / submitted / passed / failed
}

type System struct{ /* 自由 */ }

func NewSystem() *System
func (s *System) Add(a App)                              // 応募を1件足す
func (s *System) Apps() []App                             // 足した順に全部返す
func (s *System) Tick(now string) []string                // 毎日21:00の定期処理を now（"9/21 21:00"）で1回動かし、通知した Company を通知した順に返す
func (s *System) UserSays(text string) error              // ユーザーの発言（例 "submitted Osaka Gas"）
func (s *System) Move(company, to string) error           // company の応募の状態を to へ動かす
func (s *System) Color(status string) string              // 状態→色
func (s *System) ExtractDeadline(mail string) (string, error) // メール本文→締切 "10/15 12:00"。自信がなければ ErrAskUser を返す

var ErrAskUser = errors.New("ask user")
```
