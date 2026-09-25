package hub

// 実験の採点テスト。A・B どちらの出力にも同じものを当てる。
// 1つの Test が「1つのバグ」に対応する（落ちた Test の数 = バグの数）。
// AI には見せない。

import (
	"errors"
	"sync"
	"testing"
)

func TestSpecExampleRemind(t *testing.T) {
	s := NewSystem()
	s.Add(App{Company: "Osaka Gas", Deadline: "9/24 23:59", Status: "draft"})
	got := s.Tick("9/21 21:00")
	if len(got) != 1 || got[0] != "Osaka Gas" {
		t.Fatalf("仕様の example: got %v", got)
	}
}

func TestDueSoonFiltersStatusAndWindow(t *testing.T) {
	s := NewSystem()
	s.Add(App{Company: "late", Deadline: "9/30 10:00", Status: "draft"})
	s.Add(App{Company: "done", Deadline: "9/22 09:00", Status: "submitted"})
	s.Add(App{Company: "soon", Deadline: "9/24 23:59", Status: "draft"})
	got := s.Tick("9/21 21:00")
	if len(got) != 1 || got[0] != "soon" {
		t.Fatalf("got %v", got)
	}
}

func TestDueSoonSortedByDeadline(t *testing.T) {
	s := NewSystem()
	s.Add(App{Company: "b", Deadline: "9/24 23:59", Status: "draft"})
	s.Add(App{Company: "a", Deadline: "9/22 09:00", Status: "draft"})
	got := s.Tick("9/21 21:00")
	if len(got) != 2 || got[0] != "a" || got[1] != "b" {
		t.Fatalf("got %v", got)
	}
}

func TestFlowFollowsArrows(t *testing.T) {
	s := NewSystem()
	s.Add(App{Company: "x", Deadline: "9/24 23:59", Status: "draft"})
	if err := s.Move("x", "passed"); err == nil {
		t.Fatal("draft から passed に飛べてしまった")
	}
	if err := s.Move("x", "submitted"); err != nil {
		t.Fatal(err)
	}
	if err := s.Move("x", "passed"); err != nil {
		t.Fatal(err)
	}
	if s.Apps()[0].Status != "passed" {
		t.Fatalf("%+v", s.Apps())
	}
}

func TestOnConflictFailedWinsOverPassed(t *testing.T) {
	s := NewSystem()
	s.Add(App{Company: "x", Deadline: "9/24 23:59", Status: "submitted"})
	_ = s.Move("x", "passed")
	if err := s.Move("x", "failed"); err != nil {
		t.Fatal(err)
	}
	if s.Apps()[0].Status != "failed" {
		t.Fatalf("failed wins over passed のはずが %s", s.Apps()[0].Status)
	}
	s2 := NewSystem()
	s2.Add(App{Company: "y", Deadline: "9/24 23:59", Status: "submitted"})
	_ = s2.Move("y", "failed")
	if err := s2.Move("y", "passed"); err != nil {
		t.Fatal("failed の後の passed はエラーにしない")
	}
	if s2.Apps()[0].Status != "failed" {
		t.Fatalf("failed のままのはずが %s", s2.Apps()[0].Status)
	}
}

func TestUserSaysMovesOnlyThatCompany(t *testing.T) {
	s := NewSystem()
	s.Add(App{Company: "Osaka Gas", Deadline: "9/24 23:59", Status: "draft"})
	s.Add(App{Company: "Other", Deadline: "9/24 23:59", Status: "draft"})
	if err := s.UserSays("submitted Osaka Gas"); err != nil {
		t.Fatal(err)
	}
	apps := s.Apps()
	if apps[0].Status != "submitted" || apps[1].Status != "draft" {
		t.Fatalf("%+v", apps)
	}
}

func TestMatchColor(t *testing.T) {
	s := NewSystem()
	if s.Color("draft") != "red" || s.Color("submitted") != "gray" || s.Color("passed") != "blue" {
		t.Fatal("表")
	}
	if s.Color("failed") != "gray" || s.Color("nonsense") != "gray" {
		t.Fatal("otherwise")
	}
}

func TestExtractDeadlineExamples(t *testing.T) {
	s := NewSystem()
	cases := map[string]string{
		"10/15(木)12:00まで": "10/15 12:00",
		"【締切9/24 23:59】":  "9/24 23:59",
	}
	for in, want := range cases {
		got, err := s.ExtractDeadline(in)
		if err != nil || got != want {
			t.Errorf("%q: got %q, %v; want %q", in, got, err, want)
		}
	}
}

func TestExtractDeadlineElseAsksUser(t *testing.T) {
	s := NewSystem()
	_, err := s.ExtractDeadline("面接のご案内です。日程は追ってご連絡します。")
	if !errors.Is(err, ErrAskUser) {
		t.Fatalf("自信がないときは ErrAskUser のはずが %v", err)
	}
}

func TestSameAppIsSerialized(t *testing.T) {
	// go test -race で走らせる。同じ応募への並列な書き換えでレースが出ないこと
	s := NewSystem()
	s.Add(App{Company: "x", Deadline: "9/24 23:59", Status: "draft"})
	var wg sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_ = s.Move("x", "submitted")
			_ = s.Apps()
		}()
	}
	wg.Wait()
	if s.Apps()[0].Status != "submitted" {
		t.Fatal(s.Apps())
	}
}
