# OpenHands Factory Smoke Test

A small command-line Task Manager written in Python 3. It stores tasks in a JSON
file, so your list survives between separate command invocations.

## Requirements

- Python 3.9 or newer
- No third-party packages: the application and its tests use the standard
  library only (`argparse`, `json`, `unittest`)

## Installation

There is nothing to install. Copy or clone this repository and run the script
directly:

```bash
git clone <repository-url>
cd factory-smoke-test
python3 task_manager.py --help
```

## Usage

All commands accept an optional `--data-file PATH`. It can be given before or
after the command name, and defaults to `tasks.json` in the current directory.

Add a task:

```bash
python3 task_manager.py add "Buy groceries"
# Added task 1: Buy groceries
```

List tasks:

```bash
python3 task_manager.py list
# [ ] 1. Buy groceries
```

Complete a task by its ID:

```bash
python3 task_manager.py complete 1
# Completed task 1: Buy groceries

python3 task_manager.py list
# [x] 1. Buy groceries
```

Show only the tasks that are already complete:

```bash
python3 task_manager.py list --completed-only
# [x] 1. Buy groceries
```

If no task is complete, the command reports `No completed tasks.` and exits
with `0`. Without the flag, `list` keeps showing every task.

Show only the tasks that are still incomplete:

```bash
python3 task_manager.py list --incomplete-only
# [ ] 2. Write report
```

If every task is complete, the command reports `No incomplete tasks.` and
exits with `0`. With an empty data file it still reports `No tasks yet.`

Show only the tasks whose title contains some text:

```bash
python3 task_manager.py list --title-contains groceries
# [x] 1. Buy groceries
```

The match is a plain case-insensitive substring, so `--title-contains BUY`
finds both `Buy groceries` and `buy milk`. Unicode case folding applies too, so
`--title-contains STRASSE` finds `Straße review`. When no task matches, the
command reports `No matching tasks.` and exits with `0`. With an empty data file
it still reports `No tasks yet.`

Both filters can be combined; the result contains only tasks that satisfy each
one:

```bash
python3 task_manager.py list --completed-only --title-contains report
```

The same applies to `--incomplete-only`: it intersects with `--title-contains`
and with `--completed-only`. Combining both status filters
(`--completed-only --incomplete-only`) cannot match anything, so `list`
reports `No matching tasks.` and exits with `0`.

```bash
python3 task_manager.py list --incomplete-only --title-contains report
```

`list` never writes the data file, so filtering never changes your saved tasks.

Use a separate data file (useful for experiments or tests):

```bash
python3 task_manager.py --data-file /tmp/demo-tasks.json add "Write report"
python3 task_manager.py add "Write report" --data-file /tmp/demo-tasks.json
python3 task_manager.py list --data-file /tmp/demo-tasks.json
```

## Data file format

The data file is plain JSON:

```json
{
  "tasks": [
    { "id": 1, "title": "Buy groceries", "completed": true },
    { "id": 2, "title": "Write report", "completed": false }
  ]
}
```

IDs are never reused: a new task gets `max(existing ids) + 1`. Writes are atomic,
so an interrupted run cannot leave a truncated file.

## Behavior and exit codes

| Situation | Exit code | Output |
| --- | --- | --- |
| Command succeeds | `0` | Confirmation on stdout |
| Unknown task ID | `1` | `Error: task <id> not found.` on stderr |
| Data file is not valid JSON, or has an unexpected shape | `1` | `Error: ...` on stderr |
| Missing command, missing title/ID, empty title, non-integer ID | `2` | argparse usage error on stderr |

Completing an already-completed task succeeds and reports that it is already
complete.

## Testing

Run the full suite from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

The tests invoke the real CLI in subprocesses, each against its own temporary
JSON file, and assert exit codes, output, and on-disk state.

## Continuous integration

`.github/workflows/ci.yml` runs the same suite on every push and pull request,
against Python 3.9 through 3.13, and also smoke-tests `task_manager.py --help`.

## Project layout

```
task_manager.py                 # CLI implementation
tests/test_task_manager.py      # unittest suite
.github/workflows/ci.yml        # GitHub Actions CI
```
