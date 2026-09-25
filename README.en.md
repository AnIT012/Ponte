# Ponte

<img src="docs/logo/ponte.svg" alt="Ponte" width="96">

**[Website](https://anit012.github.io/nameless-lang/)** · **[Try it in the browser](https://anit012.github.io/nameless-lang/play.html)** · [Write from scratch](https://anit012.github.io/nameless-lang/write.html) · [日本語](README.md)


> *Ponte* is Italian for "bridge": between people and machines, and between people and AI.

**People decide. The language guards.**

Ponte is a language for the top layer of a program. You write *what you want, what must never happen, and what is still undecided*, never *how to do it*. Existing languages such as Python or Java become the layer underneath.

- What you write is a contract that is always kept. Anything left undecided stops the program before it runs, any operation you did not grant is impossible, and anything that breaks an example does not pass.
- The vocabulary is small, and you can finish a whole program on your own: even calculations and decisions can be written in Ponte's `do`.
- When you work with AI, the same spec is the AI's instructions and the contract it must keep. Unlike instructions in plain language, a misreading stops with an error.

Today it runs on the Python 3.11 standard library only, with no dependencies. JavaScript / TypeScript, Go and Java are being prepared as layers you can choose underneath.
Errors and output are in English by default; use `--lang ja` or `PONTE_LANG=ja` for Japanese. The longer documents are still Japanese only.

## Why

- Hand development to an AI and it fills whatever you did not decide with guesses; you find and fix them later, again and again.
- Plain-language instructions stay ambiguous; code is readable only to some.
- In research, a learning rate that was passed on was silently dropped inside a library, and two days of experiments were void. No error ever appeared.

The problem was not how things are written, but that there was no way to check that what was decided was really kept. Ponte is for writing what you decided and having the language check it is kept.

## Decided / left out

| | Decision | Why |
|---|---|---|
| decided | Nothing runs while something is undecided (`tbd`) | so nothing gets filled in by guessing |
| decided | An operation not granted in `who` is impossible | a forgotten permission shows up before running |
| decided | Examples are the tests (`example`) | decisions stay checkable |
| decided | The lower layer reports the values it actually used; `confirm` compares them | a value that was silently dropped stops the run |
| left out | A GUI | stay a written language; typing a heading only fills in the names of its required parts |
| left out | Depending on AI | how AI is used keeps changing; Ponte works without it, and with it the same spec is the instruction |
| left out | Research-only features | the research incidents have the same shape in apps and APIs, so they became a general part of the core |

## Example: did the value really take effect below?

```
job Train
  run      uv run python train.py
  with     learning_rate 1.25e-4, batch_size 32
  confirm  learning_rate, batch_size
  require  test_accuracy at least 52
  suspect  test_accuracy above 75
```

```
$ ponte job train.ponte Train
job Train: running
  confirm learning_rate: declared 1.25e-4, but 0.001 was actually used (stopped the run)
job Train: contract broken (1 problem(s))
```

The design and the decisions are the author's; the implementation was done with AI coding tools.

## 30 seconds

An excerpt of [spec/todo.ponte](spec/todo.ponte):

```
thing Task
  title   text
  owner   User  gone[remove too]
  status  [todo | done]

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
止まります（1件）
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
