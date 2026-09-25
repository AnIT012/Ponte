package hub

// 生成された Go の「決まった変換」が仕様どおりに動くかの手書きテスト。
// codegen のテストが生成先にコピーして go test する。

import (
	"sync"
	"testing"
	"time"
)

func TestFlowFollowsArrows(t *testing.T) {
	b := NewApplicationBox(Application{Status: "draft"})
	defer b.Close()
	if err := b.MoveStatus("passed"); err == nil {
		t.Fatal("draft から passed に飛べてしまった")
	}
	if err := b.MoveStatus("submitted"); err != nil {
		t.Fatal(err)
	}
	if err := b.MoveStatus("passed"); err != nil {
		t.Fatal(err)
	}
	if b.Get().Status != "passed" {
		t.Fatalf("got %s", b.Get().Status)
	}
}

func TestOnConflictFailedWinsOverPassed(t *testing.T) {
	// passed の後に failed が来る → failed が勝つ
	b := NewApplicationBox(Application{Status: "submitted"})
	defer b.Close()
	_ = b.MoveStatus("passed")
	if err := b.MoveStatus("failed"); err != nil {
		t.Fatal(err)
	}
	if b.Get().Status != "failed" {
		t.Fatalf("failed wins over passed のはずが %s", b.Get().Status)
	}
	// failed の後に passed が来る → 何もしない（エラーにもしない）
	b2 := NewApplicationBox(Application{Status: "submitted"})
	defer b2.Close()
	_ = b2.MoveStatus("failed")
	if err := b2.MoveStatus("passed"); err != nil {
		t.Fatal(err)
	}
	if b2.Get().Status != "failed" {
		t.Fatalf("failed のままのはずが %s", b2.Get().Status)
	}
}

func TestSameBoxIsSerialized(t *testing.T) {
	// 同じ箱への書き換えは1つずつ。並列に 1000 回足しても壊れない
	b := NewApplicationBox(Application{Company: "a"})
	defer b.Close()
	var wg sync.WaitGroup
	count := 0
	for i := 0; i < 1000; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_ = b.Update(func(cur, prev *Application) error {
				count++ // goroutine 1つが順に処理するので data race にならない
				return nil
			})
		}()
	}
	wg.Wait()
	if count != 1000 {
		t.Fatalf("count=%d", count)
	}
}

func TestListAndMatch(t *testing.T) {
	now := specTime("9/21 21:00")
	all := []Application{
		{Company: "late", Deadline: specTime("9/30 10:00"), Status: "draft"},
		{Company: "soon", Deadline: specTime("9/24 23:59"), Status: "draft"},
		{Company: "sooner", Deadline: specTime("9/22 09:00"), Status: "draft"},
		{Company: "done", Deadline: specTime("9/22 09:00"), Status: "submitted"},
	}
	got := DueSoon(all, now)
	if len(got) != 2 || got[0].Company != "sooner" || got[1].Company != "soon" {
		t.Fatalf("got %+v", got)
	}
	if ApplicationStatusToColor("passed") != "blue" || ApplicationStatusToColor("nonsense") != "gray" {
		t.Fatal("match")
	}
}

func TestUserSaysMovesOnlyNarrowedBoxes(t *testing.T) {
	s := NewStore()
	defer s.Close()
	s.AddApplication(Application{Company: "Osaka Gas", Status: "draft"})
	s.AddApplication(Application{Company: "Other", Status: "draft"})
	company, ok := MatchMarkSubmitted("submitted Osaka Gas")
	if !ok || company != "Osaka Gas" {
		t.Fatal("match failed")
	}
	if err := RuleMarkSubmitted(s, &recorder{}, time.Time{}, company); err != nil {
		t.Fatal(err)
	}
	all := s.AllApplications()
	if all[0].Status != "submitted" || all[1].Status != "draft" {
		t.Fatalf("%+v", all)
	}
}
