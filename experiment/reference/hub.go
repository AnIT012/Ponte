package hub

// 実験ハーネス（harness_test.go）が通せることを示す参照実装。
// AI の出力ではない。採点パイプラインの検算に使う。

import (
	"errors"
	"fmt"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"
)

type App struct {
	Company  string
	Deadline string
	Status   string
}

var ErrAskUser = errors.New("ask user")

type box struct {
	mu   sync.Mutex
	app  App
	prev string
}

type System struct {
	mu    sync.RWMutex
	boxes []*box
}

func NewSystem() *System { return &System{} }

func (s *System) Add(a App) {
	s.mu.Lock()
	s.boxes = append(s.boxes, &box{app: a, prev: a.Status})
	s.mu.Unlock()
}

func (s *System) Apps() []App {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]App, 0, len(s.boxes))
	for _, b := range s.boxes {
		b.mu.Lock()
		out = append(out, b.app)
		b.mu.Unlock()
	}
	return out
}

func parseTime(s string) (time.Time, error) { return time.Parse("1/2 15:04", s) }

func endOfDay(t time.Time) time.Time {
	y, m, d := t.Date()
	return time.Date(y, m, d, 23, 59, 59, 0, time.UTC)
}

func (s *System) dueSoon(now time.Time) []App {
	var out []App
	for _, a := range s.Apps() {
		if a.Status != "draft" {
			continue
		}
		d, err := parseTime(a.Deadline)
		if err != nil || d.Before(now) || d.After(endOfDay(now.AddDate(0, 0, 3))) {
			continue
		}
		out = append(out, a)
	}
	sort.SliceStable(out, func(i, j int) bool {
		di, _ := parseTime(out[i].Deadline)
		dj, _ := parseTime(out[j].Deadline)
		return di.Before(dj)
	})
	return out
}

func (s *System) Tick(now string) []string {
	t, err := parseTime(now)
	if err != nil {
		return nil
	}
	var names []string
	for _, a := range s.dueSoon(t) {
		names = append(names, a.Company)
	}
	return names
}

var transitions = map[string][]string{
	"draft":     {"submitted"},
	"submitted": {"passed", "failed"},
}

func canMove(from, to string) bool {
	for _, d := range transitions[from] {
		if d == to {
			return true
		}
	}
	return false
}

func (b *box) move(to string) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	cur := b.app.Status
	if cur == to {
		return nil
	}
	if canMove(cur, to) {
		b.prev = cur
		b.app.Status = to
		return nil
	}
	if canMove(b.prev, to) && canMove(b.prev, cur) {
		if to == "failed" && cur == "passed" {
			b.app.Status = to
			return nil
		}
		if to == "passed" && cur == "failed" {
			return nil
		}
	}
	return fmt.Errorf("%s から %s へは動けません", cur, to)
}

func (s *System) Move(company, to string) error {
	s.mu.RLock()
	boxes := append([]*box(nil), s.boxes...)
	s.mu.RUnlock()
	var wg sync.WaitGroup
	var mu sync.Mutex
	var first error
	for _, b := range boxes {
		b.mu.Lock()
		match := b.app.Company == company
		b.mu.Unlock()
		if !match {
			continue
		}
		wg.Add(1)
		go func(b *box) {
			defer wg.Done()
			if err := b.move(to); err != nil {
				mu.Lock()
				if first == nil {
					first = err
				}
				mu.Unlock()
			}
		}(b)
	}
	wg.Wait()
	return first
}

var saysSubmitted = regexp.MustCompile(`^submitted (.+)$`)

func (s *System) UserSays(text string) error {
	if m := saysSubmitted.FindStringSubmatch(text); m != nil {
		return s.Move(m[1], "submitted")
	}
	return nil
}

func (s *System) Color(status string) string {
	switch status {
	case "draft":
		return "red"
	case "submitted":
		return "gray"
	case "passed":
		return "blue"
	default:
		return "gray"
	}
}

var deadlineRe = regexp.MustCompile(`(\d{1,2})/(\d{1,2})(?:\([^)]*\))?\s*(\d{1,2}):(\d{2})`)

func (s *System) ExtractDeadline(mail string) (string, error) {
	m := deadlineRe.FindAllStringSubmatch(mail, -1)
	if len(m) != 1 {
		return "", ErrAskUser
	}
	return strings.TrimLeft(m[0][1], "0") + "/" + strings.TrimLeft(m[0][2], "0") + " " + m[0][3] + ":" + m[0][4], nil
}
