# Ponte

> *Ponte* is Italian for "bridge" — between people and AI, and between the rules you write and the Python that runs them.

**People decide. AI writes. The language guards.**

When you ask an AI to build an app, the hardest problem is not that it writes bad code — it is that it quietly **decides things you never decided**. In Ponte you only write *what you want, what must never happen, and what you have not decided yet*.

- Everything decided (data shapes, state flows, who may do what, screens) is run by the language itself.
- The AI only fills small, contracted holes (examples, forbidden behaviours, a fallback).
- Anything left undecided **stops the app before it runs**.

No dependencies: Python 3.11 standard library only. (The documentation and error messages are in Japanese.)

## 30 seconds

An excerpt of [spec/todo.ponte](spec/todo.ponte):

```
thing Task
  title   text
  owner   User  gone[remove too]
  status[todo | done]

flow Task.status
  todo -> done -> todo

who
  user  can see     Task  where owner is me
  user  can change  Task  where owner is me

rule Finish
  why    finished tasks should go away
  when   user taps done-button on Task
  where  status is todo
  do     move this to done
  example
    given   Task
      title   "buy milk"
      status  todo
    taps    done-button on Task
      title   "buy milk"
    expect  Task is done
      title   "buy milk"
```

Typos and forgotten decisions stop before anything runs (close misspellings also get a "did you mean …?"):

```
$ python -m ponte check todo.ponte
渡せません（1件）
  todo.ponte:20  E32  rule Finish: Task に「finished」という状態はありません（todo / done）
```

`ponte test` runs every `example`, and also reports what no example has checked yet (a rule without examples, a flow arrow nobody walks).

## Getting started

```
git clone https://github.com/AnIT012/nameless-lang
cd nameless-lang
python -m ponte run spec/todo.ponte          # → http://127.0.0.1:8000/
```

Or try it in the browser without installing anything: the homepage's **試す** (playground) page runs the real checker via Pyodide.

## What's in the box

| Command | What it does |
|---|---|
| `ponte check app.ponte` | Find undecided or wrong things (`--json` for tools) |
| `ponte test app.ponte` | Run all examples; list unchecked places (`--strict` makes them fail) |
| `ponte run app.ponte` | Run the app with a browser UI. `--login` for real password login, `--reload` while editing |
| `ponte fill app.ponte` | Let an AI write the body of each `action`, verified against its examples and `never`s |
| `ponte doc app.ponte` | A one-page HTML of every decision, for people who don't read code |
| `ponte explain E32` | Why an error stops you, and how to fix it |
| `ponte lsp` | Language server (diagnostics, hover, completion) for any editor |
| `ponte fmt` / `build` / `new` / `data` | Format, bundle into one `.pyz`, start from a template, export/import/compact data |

The language parts: `thing` (data), `flow` (state transitions), `who` (permissions — anything not written is forbidden), `list`, `rule` (trigger → one action, with examples), `relate` (then / before / else between rules), `action` (an AI-filled hole with a contract), screens (`scene`, `look`, `part`, `input`, `style`, `words`), `use std/...` (standard library), and `tbd` (not decided yet — blocks running).

Full specification (Japanese): [docs/言語仕様_v0.3.md](docs/言語仕様_v0.3.md). Tutorial: [docs/入門.md](docs/入門.md).

## Limits (honestly)

- Login is name + password only (no e-mail verification or password reset yet).
- Only what examples and `never`s say can be guaranteed. Ponte shows what is unchecked, but people still have to write it.
- The toolset for AI-written bodies is deliberately small (no loops, no regex — `shape` instead).
- Notifications stay inside the app; sending real e-mail or chat messages (`connect … does`) is only a declared shape so far.
- Single machine, single append-only data file. Not meant for large multi-server services.
