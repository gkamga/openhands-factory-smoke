"""End-to-end tests for task_manager.py, driven through the real CLI."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_ROOT, "task_manager.py")


class TaskManagerCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_file = os.path.join(self._tmp.name, "tasks.json")

    def run_cli(self, *args, data_file=None, cwd=REPO_ROOT):
        command = [sys.executable, SCRIPT]
        if data_file is not False:
            command += ["--data-file", data_file or self.data_file]
        command += list(args)
        return subprocess.run(command, capture_output=True, text=True, cwd=cwd)

    def read_tasks(self):
        with open(self.data_file, "r", encoding="utf-8") as handle:
            return json.load(handle)["tasks"]

    def write_raw(self, content):
        with open(self.data_file, "w", encoding="utf-8") as handle:
            handle.write(content)

    def write_raw_bytes(self, content):
        with open(self.data_file, "wb") as handle:
            handle.write(content)

    def seed_tasks(self, tasks):
        self.write_raw(json.dumps({"tasks": tasks}))

    def test_add_creates_task_with_expected_fields(self):
        result = self.run_cli("add", "Buy groceries")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Added task 1: Buy groceries", result.stdout)
        self.assertEqual(
            self.read_tasks(),
            [{"id": 1, "title": "Buy groceries", "completed": False}],
        )

    def test_add_persists_across_separate_executions(self):
        self.assertEqual(self.run_cli("add", "First task").returncode, 0)
        self.assertEqual(self.run_cli("add", "Second task").returncode, 0)

        result = self.run_cli("list")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            ["[ ] 1. First task", "[ ] 2. Second task"],
        )

    def test_add_assigns_incrementing_unique_ids(self):
        for title in ("One", "Two", "Three"):
            self.assertEqual(self.run_cli("add", title).returncode, 0)

        ids = [task["id"] for task in self.read_tasks()]

        self.assertEqual(ids, [1, 2, 3])
        self.assertEqual(len(ids), len(set(ids)))

    def test_complete_marks_task_complete_and_persists(self):
        self.assertEqual(self.run_cli("add", "Write tests").returncode, 0)

        result = self.run_cli("complete", "1")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Completed task 1: Write tests", result.stdout)
        self.assertTrue(self.read_tasks()[0]["completed"])

        listing = self.run_cli("list")
        self.assertEqual(listing.stdout.splitlines(), ["[x] 1. Write tests"])

    def test_complete_leaves_other_tasks_untouched(self):
        self.run_cli("add", "One")
        self.run_cli("add", "Two")
        self.assertEqual(self.run_cli("complete", "2").returncode, 0)

        tasks = self.read_tasks()

        self.assertFalse(tasks[0]["completed"])
        self.assertTrue(tasks[1]["completed"])

    def test_complete_unknown_id_fails(self):
        self.run_cli("add", "Only task")

        result = self.run_cli("complete", "99")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Error: task 99 not found.", result.stderr)
        self.assertFalse(self.read_tasks()[0]["completed"])

    def test_complete_non_integer_id_fails(self):
        result = self.run_cli("complete", "abc")

        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid int value", result.stderr)

    def test_complete_without_id_fails(self):
        result = self.run_cli("complete")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required", result.stderr)

    def test_complete_twice_is_idempotent(self):
        self.run_cli("add", "Repeat")

        self.assertEqual(self.run_cli("complete", "1").returncode, 0)
        second = self.run_cli("complete", "1")

        self.assertEqual(second.returncode, 0)
        self.assertIn("already complete", second.stdout)
        self.assertTrue(self.read_tasks()[0]["completed"])

    def test_add_without_title_fails(self):
        result = self.run_cli("add")

        self.assertEqual(result.returncode, 2)
        self.assertIn("required", result.stderr)
        self.assertFalse(os.path.exists(self.data_file))

    def test_add_empty_title_fails(self):
        result = self.run_cli("add", "")

        self.assertEqual(result.returncode, 2)
        self.assertIn("task title must not be empty", result.stderr)
        self.assertFalse(os.path.exists(self.data_file))

    def test_add_whitespace_title_fails(self):
        result = self.run_cli("add", "   ")

        self.assertEqual(result.returncode, 2)
        self.assertIn("task title must not be empty", result.stderr)

    def test_add_strips_surrounding_whitespace(self):
        result = self.run_cli("add", "  Padded title  ")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_tasks()[0]["title"], "Padded title")

    def test_list_with_no_data_file_reports_empty(self):
        result = self.run_cli("list")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "No tasks yet.")
        self.assertFalse(os.path.exists(self.data_file))

    def test_list_shows_completed_and_incomplete_tasks_together(self):
        self.run_cli("add", "Done")
        self.run_cli("add", "Pending")
        self.run_cli("complete", "1")

        result = self.run_cli("list")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(), ["[x] 1. Done", "[ ] 2. Pending"]
        )

    def test_list_completed_only_shows_only_completed_tasks(self):
        for title in ("Done", "Pending", "Also done"):
            self.assertEqual(self.run_cli("add", title).returncode, 0)
        self.run_cli("complete", "1")
        self.run_cli("complete", "3")

        result = self.run_cli("list", "--completed-only")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(), ["[x] 1. Done", "[x] 3. Also done"]
        )

    def test_list_completed_only_without_completed_tasks_reports_empty(self):
        self.run_cli("add", "Pending")

        result = self.run_cli("list", "--completed-only")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "No completed tasks.")

    def test_list_completed_only_with_no_tasks_reports_empty(self):
        result = self.run_cli("list", "--completed-only")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "No tasks yet.")
        self.assertFalse(os.path.exists(self.data_file))

    def test_list_completed_only_works_with_subcommand_data_file(self):
        self.write_raw(
            json.dumps(
                {
                    "tasks": [
                        {"id": 1, "title": "Done", "completed": True},
                        {"id": 2, "title": "Pending", "completed": False},
                    ]
                }
            )
        )

        result = self.run_cli(
            "list",
            "--completed-only",
            "--data-file",
            self.data_file,
            data_file=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["[x] 1. Done"])

    def test_list_completed_only_leaves_data_file_unchanged(self):
        self.write_raw(
            json.dumps(
                {
                    "tasks": [
                        {"id": 1, "title": "Done", "completed": True},
                        {"id": 2, "title": "Pending", "completed": False},
                    ]
                }
            )
        )
        with open(self.data_file, "r", encoding="utf-8") as handle:
            original = handle.read()

        result = self.run_cli("list", "--completed-only")

        self.assertEqual(result.returncode, 0, result.stderr)
        with open(self.data_file, "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), original)

    def test_data_file_option_after_subcommand(self):
        result = self.run_cli("add", "--data-file", self.data_file, "After option")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_tasks()[0]["title"], "After option")

    def test_data_file_option_before_subcommand(self):
        result = self.run_cli("--data-file", self.data_file, "add", "Before option")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_tasks()[0]["title"], "Before option")

    def test_default_data_file_is_used_in_working_directory(self):
        result = self.run_cli(
            "add", "Default path", data_file=False, cwd=self._tmp.name
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        default_path = os.path.join(self._tmp.name, "tasks.json")
        self.assertTrue(os.path.exists(default_path))
        with open(default_path, "r", encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["tasks"][0]["title"], "Default path")

    def test_list_title_filter_matches_case_insensitively(self):
        self.seed_tasks(
            [
                {"id": 1, "title": "Buy groceries", "completed": False},
                {"id": 2, "title": "buy milk", "completed": False},
                {"id": 3, "title": "Write report", "completed": False},
            ]
        )

        result = self.run_cli("list", "--title-contains", "BUY")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            ["[ ] 1. Buy groceries", "[ ] 2. buy milk"],
        )

    def test_list_title_filter_matches_substring_anywhere(self):
        self.seed_tasks(
            [
                {"id": 1, "title": "Write quarterly report", "completed": False},
                {"id": 2, "title": "Read a book", "completed": False},
            ]
        )

        result = self.run_cli("list", "--title-contains", "quarter")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["[ ] 1. Write quarterly report"])

    def test_list_title_filter_treats_text_literally(self):
        self.seed_tasks(
            [
                {"id": 1, "title": "Ship C++ build", "completed": False},
                {"id": 2, "title": "Ship C build", "completed": False},
            ]
        )

        result = self.run_cli("list", "--title-contains", "C++")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["[ ] 1. Ship C++ build"])

    def test_list_title_filter_is_case_insensitive_for_unicode(self):
        self.seed_tasks(
            [
                {"id": 1, "title": "Café planning", "completed": False},
                {"id": 2, "title": "Other work", "completed": False},
            ]
        )

        result = self.run_cli("list", "--title-contains", "CAFÉ")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["[ ] 1. Café planning"])

    def test_list_title_filter_without_match_reports_empty(self):
        self.seed_tasks([{"id": 1, "title": "Write report", "completed": False}])

        result = self.run_cli("list", "--title-contains", "groceries")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "No matching tasks.")

    def test_list_title_filter_with_no_tasks_reports_empty(self):
        result = self.run_cli("list", "--title-contains", "anything")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "No tasks yet.")
        self.assertFalse(os.path.exists(self.data_file))

    def test_list_title_filter_combines_with_completed_only(self):
        self.seed_tasks(
            [
                {"id": 1, "title": "Buy groceries", "completed": True},
                {"id": 2, "title": "Buy stamps", "completed": False},
                {"id": 3, "title": "Write report", "completed": True},
            ]
        )

        result = self.run_cli(
            "list", "--completed-only", "--title-contains", "buy"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["[x] 1. Buy groceries"])

    def test_list_title_filter_combined_with_completed_only_no_match(self):
        self.seed_tasks(
            [
                {"id": 1, "title": "Buy stamps", "completed": False},
                {"id": 2, "title": "Write report", "completed": True},
            ]
        )

        result = self.run_cli(
            "list", "--completed-only", "--title-contains", "buy"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "No matching tasks.")

    def test_list_title_filter_leaves_data_file_unchanged(self):
        self.seed_tasks(
            [
                {"id": 1, "title": "Buy groceries", "completed": False},
                {"id": 2, "title": "Write report", "completed": True},
            ]
        )
        with open(self.data_file, "r", encoding="utf-8") as handle:
            original = handle.read()

        result = self.run_cli("list", "--title-contains", "buy")

        self.assertEqual(result.returncode, 0, result.stderr)
        with open(self.data_file, "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), original)

    def test_list_title_filter_works_with_subcommand_data_file(self):
        self.seed_tasks([{"id": 1, "title": "Buy groceries", "completed": False}])

        result = self.run_cli(
            "list",
            "--title-contains",
            "buy",
            "--data-file",
            self.data_file,
            data_file=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["[ ] 1. Buy groceries"])

    def test_list_title_filter_accepts_data_file_before_subcommand(self):
        self.seed_tasks([{"id": 1, "title": "Buy groceries", "completed": False}])

        result = self.run_cli(
            "--data-file",
            self.data_file,
            "list",
            "--title-contains",
            "buy",
            data_file=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["[ ] 1. Buy groceries"])

    def test_titles_with_unicode_and_quotes_round_trip(self):
        title = 'Café "meeting" — 09:00'
        self.assertEqual(self.run_cli("add", title).returncode, 0)

        result = self.run_cli("list")

        self.assertIn(title, result.stdout)
        self.assertEqual(self.read_tasks()[0]["title"], title)

    def test_corrupt_data_file_reports_error(self):
        self.write_raw("{not json")

        result = self.run_cli("list")

        self.assertEqual(result.returncode, 1)
        self.assertIn("is not valid JSON", result.stderr)

    def test_unexpected_data_file_format_reports_error(self):
        self.write_raw(json.dumps(["not", "a", "dict"]))

        result = self.run_cli("list")

        self.assertEqual(result.returncode, 1)
        self.assertIn("unexpected format", result.stderr)

    def test_boolean_task_ids_in_persisted_data_are_rejected(self):
        for boolean_id in (True, False):
            with self.subTest(task_id=boolean_id):
                self.write_raw(
                    json.dumps(
                        {
                            "tasks": [
                                {
                                    "id": boolean_id,
                                    "title": "Sneaky task",
                                    "completed": False,
                                }
                            ]
                        }
                    )
                )

                result = self.run_cli("list")

                self.assertEqual(result.returncode, 1)
                self.assertIn("contains a malformed task", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_invalid_stored_task_ids_are_rejected(self):
        for bad_id in ("1", 1.5, None, [1], {"value": 1}):
            with self.subTest(task_id=bad_id):
                self.write_raw(
                    json.dumps(
                        {
                            "tasks": [
                                {
                                    "id": bad_id,
                                    "title": "Bad id",
                                    "completed": False,
                                }
                            ]
                        }
                    )
                )

                result = self.run_cli("list")

                self.assertEqual(result.returncode, 1)
                self.assertIn("contains a malformed task", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_valid_integer_task_ids_still_load(self):
        self.write_raw(
            json.dumps(
                {
                    "tasks": [
                        {"id": 0, "title": "Zero", "completed": False},
                        {"id": 7, "title": "Seven", "completed": True},
                    ]
                }
            )
        )

        result = self.run_cli("list")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(), ["[ ] 0. Zero", "[x] 7. Seven"]
        )

    def test_invalid_utf8_data_file_reports_error(self):
        self.write_raw_bytes(
            b'{"tasks": [{"id": 1, "title": "caf\xff", "completed": false}]}'
        )

        result = self.run_cli("list")

        self.assertEqual(result.returncode, 1)
        self.assertIn("is not valid UTF-8", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_invalid_utf8_data_file_is_not_overwritten_by_add(self):
        original = b"\xff\xfe not utf-8"
        self.write_raw_bytes(original)

        result = self.run_cli("add", "New task")

        self.assertEqual(result.returncode, 1)
        self.assertIn("is not valid UTF-8", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        with open(self.data_file, "rb") as handle:
            self.assertEqual(handle.read(), original)

    def test_count_with_no_data_file_reports_zero(self):
        result = self.run_cli("count")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "Total tasks: 0")
        self.assertFalse(os.path.exists(self.data_file))

    def test_count_with_empty_data_file_reports_zero(self):
        self.seed_tasks([])

        result = self.run_cli("count")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "Total tasks: 0")

    def test_count_includes_completed_tasks(self):
        self.seed_tasks(
            [
                {"id": 1, "title": "Done", "completed": True},
                {"id": 2, "title": "Pending", "completed": False},
                {"id": 3, "title": "Also done", "completed": True},
            ]
        )

        result = self.run_cli("count")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "Total tasks: 3")

    def test_count_reflects_tasks_added_through_the_cli(self):
        self.run_cli("add", "One")
        self.run_cli("add", "Two")
        self.run_cli("complete", "1")

        result = self.run_cli("count")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "Total tasks: 2")

    def test_count_leaves_data_file_unchanged(self):
        self.seed_tasks(
            [
                {"id": 1, "title": "Done", "completed": True},
                {"id": 2, "title": "Pending", "completed": False},
            ]
        )
        with open(self.data_file, "r", encoding="utf-8") as handle:
            original = handle.read()

        result = self.run_cli("count")

        self.assertEqual(result.returncode, 0, result.stderr)
        with open(self.data_file, "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), original)

    def test_count_accepts_data_file_after_subcommand(self):
        self.seed_tasks([{"id": 1, "title": "Buy groceries", "completed": False}])

        result = self.run_cli("count", "--data-file", self.data_file, data_file=False)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "Total tasks: 1")

    def test_count_accepts_data_file_before_subcommand(self):
        self.seed_tasks([{"id": 1, "title": "Buy groceries", "completed": False}])

        result = self.run_cli("--data-file", self.data_file, "count", data_file=False)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "Total tasks: 1")

    def test_count_corrupt_data_file_reports_error(self):
        self.write_raw("{not json")

        result = self.run_cli("count")

        self.assertEqual(result.returncode, 1)
        self.assertIn("is not valid JSON", result.stderr)

    def test_missing_command_fails(self):
        result = self.run_cli()

        self.assertEqual(result.returncode, 2)
        self.assertIn("required", result.stderr)


class TaskManagerModuleTests(unittest.TestCase):
    def test_next_task_id_starts_at_one_and_continues(self):
        sys.path.insert(0, REPO_ROOT)
        try:
            import task_manager
        finally:
            sys.path.pop(0)

        self.assertEqual(task_manager.next_task_id([]), 1)
        self.assertEqual(
            task_manager.next_task_id([{"id": 3, "title": "a", "completed": False}]),
            4,
        )


if __name__ == "__main__":
    unittest.main()
