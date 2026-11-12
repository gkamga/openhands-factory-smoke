"""A small command-line task manager backed by a JSON file."""

import argparse
import json
import os
import sys
import tempfile

DEFAULT_DATA_FILE = "tasks.json"


def non_empty_title(value):
    """Argparse type that strips whitespace and rejects empty titles."""
    title = value.strip()
    if not title:
        raise argparse.ArgumentTypeError("task title must not be empty")
    return title


def load_tasks(path):
    """Return the list of tasks stored at ``path`` (empty list if absent)."""
    if not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except UnicodeDecodeError as exc:
        raise ValueError(f"data file {path} is not valid UTF-8 ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"data file {path} is not valid JSON ({exc})") from exc
    except OSError as exc:
        raise ValueError(f"cannot read data file {path} ({exc})") from exc

    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise ValueError(f"data file {path} has an unexpected format")

    tasks = data["tasks"]
    for task in tasks:
        if (
            not isinstance(task, dict)
            # bool is an int subclass, so "id": true would otherwise pass
            or isinstance(task.get("id"), bool)
            or not isinstance(task.get("id"), int)
            or not isinstance(task.get("title"), str)
            or not isinstance(task.get("completed"), bool)
        ):
            raise ValueError(f"data file {path} contains a malformed task")
    return tasks


def save_tasks(path, tasks):
    """Write tasks atomically so a crash cannot leave a half-written file."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    payload = json.dumps({"tasks": tasks}, indent=2, ensure_ascii=False) + "\n"

    handle_fd, temp_path = tempfile.mkstemp(
        dir=directory, prefix=".tasks-", suffix=".tmp"
    )
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temp_path, path)
    except BaseException:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def next_task_id(tasks):
    return max((task["id"] for task in tasks), default=0) + 1


def find_task(tasks, task_id):
    for task in tasks:
        if task["id"] == task_id:
            return task
    return None


def add_task(tasks, title):
    task = {"id": next_task_id(tasks), "title": title, "completed": False}
    tasks.append(task)
    return task


def cmd_add(tasks, title, data_path):
    task = add_task(tasks, title)
    save_tasks(data_path, tasks)
    print(f"Added task {task['id']}: {task['title']}")
    return 0


def cmd_list(tasks, completed_only=False, incomplete_only=False, title_contains=None):
    visible = tasks
    if completed_only:
        visible = [task for task in visible if task["completed"]]
    if incomplete_only:
        visible = [task for task in visible if not task["completed"]]
    if title_contains is not None:
        # casefold() gives a case-insensitive match that also works for
        # non-ASCII titles, unlike lower().
        needle = title_contains.casefold()
        visible = [task for task in visible if needle in task["title"].casefold()]
    if not visible:
        if not tasks:
            print("No tasks yet.")
        elif completed_only and incomplete_only:
            # Both status filters are contradictory, so nothing can match.
            print("No matching tasks.")
        elif title_contains is not None:
            print("No matching tasks.")
        elif completed_only:
            print("No completed tasks.")
        else:
            print("No incomplete tasks.")
        return 0
    for task in visible:
        status = "x" if task["completed"] else " "
        print(f"[{status}] {task['id']}. {task['title']}")
    return 0


def cmd_complete(tasks, task_id, data_path):
    task = find_task(tasks, task_id)
    if task is None:
        print(f"Error: task {task_id} not found.", file=sys.stderr)
        return 1
    if task["completed"]:
        print(f"Task {task['id']} is already complete: {task['title']}")
        return 0

    task["completed"] = True
    save_tasks(data_path, tasks)
    print(f"Completed task {task['id']}: {task['title']}")
    return 0


def add_data_file_option(parser, default):
    parser.add_argument(
        "--data-file",
        dest="data_file",
        default=default,
        metavar="PATH",
        help="path to the JSON data file (default: tasks.json)",
    )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="task_manager.py",
        description="Manage a simple task list stored in a JSON file.",
    )
    add_data_file_option(parser, default=None)

    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    add_parser = subparsers.add_parser("add", help="add a new task")
    add_parser.add_argument("title", type=non_empty_title, help="title of the task")
    # SUPPRESS keeps this sub-option from clobbering the top-level --data-file.
    add_data_file_option(add_parser, default=argparse.SUPPRESS)

    list_parser = subparsers.add_parser("list", help="list tasks")
    list_parser.add_argument(
        "--completed-only",
        action="store_true",
        help="show only completed tasks",
    )
    list_parser.add_argument(
        "--incomplete-only",
        dest="incomplete_only",
        action="store_true",
        help="show only incomplete tasks",
    )
    list_parser.add_argument(
        "--title-contains",
        dest="title_contains",
        default=None,
        metavar="TEXT",
        help="show only tasks whose title contains TEXT (case-insensitive)",
    )
    add_data_file_option(list_parser, default=argparse.SUPPRESS)

    complete_parser = subparsers.add_parser("complete", help="mark a task as complete")
    complete_parser.add_argument("task_id", type=int, metavar="ID", help="task ID")
    add_data_file_option(complete_parser, default=argparse.SUPPRESS)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    data_path = args.data_file or DEFAULT_DATA_FILE

    try:
        tasks = load_tasks(data_path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        if args.command == "add":
            return cmd_add(tasks, args.title, data_path)
        if args.command == "list":
            return cmd_list(
                tasks,
                completed_only=args.completed_only,
                incomplete_only=args.incomplete_only,
                title_contains=args.title_contains,
            )
        return cmd_complete(tasks, args.task_id, data_path)
    except OSError as exc:
        print(f"Error: cannot write data file {data_path} ({exc})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
