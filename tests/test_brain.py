"""Behavior tests use an independent kit copy and never touch user settings."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parent.parent


class KitTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="brain-test-")
        self.base = Path(self.temp.name)
        self.root = self.base / "空白 日本語 kit"
        shutil.copytree(SOURCE, self.root, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.rmtree(self.root / "notes")
        self.run_cli("setup")

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args, expected=0, data=None, cwd=None):
        result = subprocess.run(
            [sys.executable, "-B", str(self.root / "scripts/brain.py"), *args],
            input=data, capture_output=True, encoding="utf-8", cwd=cwd or self.root,
        )
        self.assertEqual(result.returncode, expected, result.stderr + result.stdout)
        return result

    def test_setup_preserves_existing_and_is_idempotent(self):
        purpose = self.root / "notes/personal/PURPOSE.md"
        purpose.write_text("自分の目的\n", encoding="utf-8")
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertIn("0 files created", self.run_cli("setup").stdout)
        self.run_cli("setup")
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_setup_restores_only_missing_file(self):
        (self.root / "notes/work/HANDOFF.md").unlink()
        self.assertIn("1 files created", self.run_cli("setup").stdout)

    def test_setup_preflight_refuses_conflict(self):
        destination = self.root / "notes/work/HANDOFF.md"
        destination.unlink()
        destination.mkdir()
        missing = self.root / "notes/school/INDEX.md"
        missing.unlink()
        self.run_cli("setup", expected=1)
        self.assertFalse(missing.exists())

    def test_record_search_and_no_overwrite(self):
        record = self.run_cli("record", "--domain", "personal", "--name", "企画_一回目", "--stdin",
                              data="# 決定\n対象読者を先に選ぶ。\n")
        self.assertEqual(record.stdout.strip(), "notes/personal/records/企画_一回目.md")
        self.assertIn("対象読者", self.run_cli("search", "対象読者", "--domain", "personal").stdout)
        before = (self.root / record.stdout.strip()).read_bytes()
        self.run_cli("record", "--domain", "personal", "--name", "企画_一回目", "--text", "変更", expected=1)
        self.assertEqual(before, (self.root / record.stdout.strip()).read_bytes())

    def test_search_does_not_leak_other_domain(self):
        for domain in ("school", "work", "personal"):
            self.run_cli("record", "--domain", domain, "--name", "decision", "--text", f"needle {domain}")
        result = self.run_cli("search", "NEEDLE", "--domain", "school").stdout
        self.assertIn("needle school", result)
        self.assertNotIn("needle work", result)
        self.assertNotIn("needle personal", result)
        self.run_cli("search", "needle", expected=2)

    def test_search_casefold_limit_and_empty_query(self):
        self.run_cli("record", "--domain", "school", "--name", "lines", "--text", "Apple\napple\nAPPLE")
        result = self.run_cli("search", "APPLE", "--domain", "school", "--limit", "2").stdout
        self.assertEqual(result.count("notes/school/records/lines.md:"), 2)
        self.assertIn("limit reached", result)
        self.run_cli("search", " ", "--domain", "school", expected=1)
        self.run_cli("search", "a", "--domain", "school", "--limit", "0", expected=2)

    def test_record_path_constraints_and_empty_input(self):
        for name in ("../escape", "a/b", "a\\b", ".hidden", "CON", "nul", "COM1", "a:stream", "trailing.", "a" * 65):
            self.run_cli("record", "--domain", "work", "--name", name, "--text", "text", expected=1)
        self.run_cli("record", "--domain", "work", "--name", "empty", "--text", " ", expected=1)
        self.assertEqual(list((self.root / "notes/work/records").glob("*")), [])

    def test_cwd_does_not_change_write_destination_or_home(self):
        outside = self.base / "other"
        outside.mkdir()
        self.run_cli("record", "--domain", "personal", "--name", "cwd", "--text", "local", cwd=outside)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertTrue((self.root / "notes/personal/records/cwd.md").is_file())
        self.assertFalse((self.base / ".claude").exists())

    @unittest.skipIf(sys.platform == "win32", "symlink creation may need Windows privilege")
    def test_symlink_directory_refuses_setup_search_record(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "private.md").write_text("private needle", encoding="utf-8")
        shutil.rmtree(self.root / "notes/work")
        (self.root / "notes/work").symlink_to(outside, target_is_directory=True)
        for args in (("setup",), ("search", "needle", "--domain", "work"),
                     ("record", "--domain", "work", "--name", "escape", "--text", "data")):
            result = self.run_cli(*args, expected=1)
            self.assertNotIn("private needle", result.stdout)
        self.assertEqual(len(list(outside.iterdir())), 1)

    @unittest.skipIf(sys.platform == "win32", "symlink creation may need Windows privilege")
    def test_search_skips_file_and_directory_links_to_other_domain(self):
        (self.root / "notes/work/private.md").write_text("classified needle", encoding="utf-8")
        (self.root / "notes/school/link.md").symlink_to(self.root / "notes/work/private.md")
        (self.root / "notes/school/cross").symlink_to(self.root / "notes/work", target_is_directory=True)
        self.assertIn("0 matches", self.run_cli("search", "needle", "--domain", "school").stdout)

    @unittest.skipIf(sys.platform == "win32", "symlink creation may need Windows privilege")
    def test_record_refuses_dangling_file_link(self):
        (self.root / "notes/work/records/escape.md").symlink_to(self.base / "not-created.md")
        self.run_cli("record", "--domain", "work", "--name", "escape", "--text", "data", expected=1)
        self.assertFalse((self.base / "not-created.md").exists())

    def test_doctor_and_hook_json_output(self):
        self.assertIn("doctor: OK", self.run_cli("doctor").stdout)
        result = subprocess.run([sys.executable, "-B", str(self.root / "scripts/session_start.py")],
                                capture_output=True, text=True, check=True)
        output = json.loads(result.stdout)
        self.assertEqual(set(output), {"hookSpecificOutput"})
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("BRAIN-START", output["hookSpecificOutput"]["additionalContext"])
        (self.root / ".zed/settings.json").write_text("{", encoding="utf-8")
        self.run_cli("doctor", expected=1)

    def test_mac_config_commands_in_space_path(self):
        for host in ("claude", "codex"):
            data = json.loads((self.root / f"docs/hooks/{host}-mac.json").read_text())
            handler = data["hooks"]["SessionStart"][0]["hooks"][0]
            env = dict(__import__("os").environ, CLAUDE_PROJECT_DIR=str(self.root))
            if "args" in handler:
                argv = [handler["command"]] + [a.replace("${CLAUDE_PROJECT_DIR}", str(self.root)) for a in handler["args"]]
                result = subprocess.run(argv, capture_output=True, text=True, cwd=self.root, env=env)
            else:
                result = subprocess.run(handler["command"], shell=True, capture_output=True, text=True, cwd=self.root, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("BRAIN-START", json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"])

    def test_skills_and_conditional_rules(self):
        for skill in ("brain-context", "brain-record"):
            first = (self.root / f".agents/skills/{skill}/SKILL.md").read_text()
            self.assertEqual(first, (self.root / f".claude/skills/{skill}/SKILL.md").read_text())
            self.assertIn(f"name: {skill}", first)
            self.assertIn("description:", first)
        for domain in ("school", "work", "personal"):
            content = (self.root / f".claude/rules/{domain}.md").read_text()
            self.assertTrue(content.startswith('---\npaths:\n'))
            self.assertIn(f'"notes/{domain}/**/*.md"', content)

    def test_domain_add_creates_notes_rules_and_index_link(self):
        index_before = (self.root / "notes/INDEX.md").read_text(encoding="utf-8")
        self.run_cli("domain", "add", "job-hunt", "--label", "就活")
        for name in ("PURPOSE.md", "INDEX.md", "HANDOFF.md"):
            self.assertTrue((self.root / f"notes/job-hunt/{name}").is_file(), name)
        self.assertTrue((self.root / "notes/job-hunt/records").is_dir())
        self.assertTrue((self.root / "notes/job-hunt/PURPOSE.md").read_text(encoding="utf-8").startswith("# 就活 の目的\n"))
        rule = (self.root / ".claude/rules/job-hunt.md").read_text(encoding="utf-8")
        self.assertTrue(rule.startswith('---\npaths:\n'))
        self.assertIn('"notes/job-hunt/**/*.md"', rule)
        self.assertIn("BRAIN-JOB-HUNT", rule)
        self.assertIn("BRAIN-JOB-HUNT", (self.root / "docs/rules/job-hunt.md").read_text(encoding="utf-8"))
        index = (self.root / "notes/INDEX.md").read_text(encoding="utf-8")
        self.assertTrue(index.startswith(index_before))
        self.assertTrue(index.endswith("- [就活](job-hunt/INDEX.md)\n"))
        self.assertIn("doctor: OK", self.run_cli("doctor").stdout)
        self.assertIn("0 files created", self.run_cli("setup").stdout)

    def test_domain_add_never_overwrites_and_checks_before_creating(self):
        existing = self.root / "docs/rules/club.md"
        existing.write_text("自分で書いたルール\n", encoding="utf-8")
        index_before = (self.root / "notes/INDEX.md").read_bytes()
        self.run_cli("domain", "add", "club", expected=1)
        self.assertEqual(existing.read_text(encoding="utf-8"), "自分で書いたルール\n")
        self.assertFalse((self.root / "notes/club").exists())
        self.assertFalse((self.root / ".claude/rules/club.md").exists())
        self.assertEqual(index_before, (self.root / "notes/INDEX.md").read_bytes())
        existing.unlink()
        self.run_cli("domain", "add", "club", "--label", "部活")
        purpose = self.root / "notes/club/PURPOSE.md"
        purpose.write_text("# 部活 の目的\n自分の目的\n", encoding="utf-8")
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        for name in ("club", "school"):
            self.run_cli("domain", "add", name, expected=1)
        (self.root / "notes/empty").mkdir()
        self.run_cli("domain", "add", "empty", expected=1)
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_domain_add_rejects_invalid_names_and_labels(self):
        before = sorted(p.relative_to(self.root) for p in self.root.rglob("*"))
        for name in ("Club", "1club", "club_a", "クラブ", "a" * 33, "con", "com1", "../x", "club/a", ""):
            self.run_cli("domain", "add", name, expected=1)
        for label in ("改行\nあり", "[リンク]", "a" * 41, " "):
            self.run_cli("domain", "add", "club", "--label", label, expected=1)
        self.assertEqual(before, sorted(p.relative_to(self.root) for p in self.root.rglob("*")))

    def test_added_domain_record_search_without_leaking(self):
        self.run_cli("domain", "add", "club", "--label", "部活")
        self.run_cli("record", "--domain", "club", "--name", "practice", "--text", "needle club")
        self.run_cli("record", "--domain", "school", "--name", "lesson", "--text", "needle school")
        club = self.run_cli("search", "needle", "--domain", "club").stdout
        self.assertIn("notes/club/records/practice.md", club)
        self.assertNotIn("needle school", club)
        self.assertNotIn("needle club", self.run_cli("search", "needle", "--domain", "school").stdout)
        self.run_cli("record", "--domain", "ghost", "--name", "x", "--text", "data", expected=1)
        self.run_cli("search", "needle", "--domain", "ghost", expected=1)
        self.assertFalse((self.root / "notes/ghost").exists())

    def test_doctor_checks_added_domains_and_ignores_other_folders(self):
        self.run_cli("domain", "add", "club", "--label", "部活")
        odd = self.root / "notes/Bad_Name"
        odd.mkdir()
        (odd / "PURPOSE.md").write_text("needle odd", encoding="utf-8")
        self.run_cli("search", "needle", "--domain", "Bad_Name", expected=1)
        self.assertIn("doctor: OK", self.run_cli("doctor").stdout)
        (self.root / "docs/rules/club.md").unlink()
        self.assertIn("missing: docs/rules/club.md", self.run_cli("doctor", expected=1).stdout)
        (self.root / "notes/club/HANDOFF.md").unlink()
        self.assertIn("1 files created", self.run_cli("setup").stdout)
        self.assertTrue((self.root / "notes/club/HANDOFF.md").read_text(encoding="utf-8").startswith("# 部活 の引継ぎ"))

    def test_distribution_scanner_detects_injected_secret(self):
        spec = importlib.util.spec_from_file_location("scanner", SOURCE / "scripts/check_distribution.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _, findings = module.scan(SOURCE)
        self.assertEqual(findings, [])
        (self.root / "accidental.txt").write_text("sk-" + "x" * 30, encoding="utf-8")
        _, findings = module.scan(self.root)
        self.assertTrue(any("token:" in finding for finding in findings))


if __name__ == "__main__":
    unittest.main()
