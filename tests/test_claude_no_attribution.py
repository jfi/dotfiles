"""Exercise the hook through its JSON/stdin contract; no Git/gh writes occur."""

import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


HOOK = Path(__file__).resolve().parents[1] / "bin" / "claude-no-attribution"
AGENT = "Update configuration\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
HUMAN = "Update configuration\n\nCo-authored-by: jfi <663625+jfi@users.noreply.github.com>"
FOOTER = "Generated with [Claude Code](https://claude.com/claude-code)"


class AttributionHookTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.cwd = Path(self.directory.name)
        (self.cwd / "nested" / "repo").mkdir(parents=True)

    def check(self, command, expected):
        result = subprocess.run(
            ["bash", str(HOOK)],
            input=json.dumps({"cwd": str(self.cwd), "tool_input": {"command": command}}),
            text=True,
            capture_output=True,
            # Deliberately different from the hook event's cwd.
            cwd=HOOK.parent,
        )
        self.assertEqual(result.returncode, expected, (command, result.stderr))
        self.assertEqual(result.stdout, "")
        if expected == 2:
            self.assertIn("Blocked:", result.stderr)
        else:
            self.assertEqual(result.stderr, "")

    def test_git_inline_and_global_options(self):
        for prefix in (
            "git commit", "git -C nested/repo commit",
            "git -Cnested -C repo -c user.name=Test --no-pager commit",
            "git --git-dir nested/repo/.git --work-tree=nested/repo commit",
            "/usr/bin/git -c core.editor=true commit",
        ):
            for option in ("-m ", "--message=", "-m"):
                with self.subTest(prefix=prefix, option=option):
                    self.check(prefix + " " + option + shlex.quote(AGENT), 2)
                    self.check(prefix + " " + option + shlex.quote(HUMAN), 0)

    def test_git_files_and_working_directories(self):
        (self.cwd / "message.txt").write_text(HUMAN)
        (self.cwd / "nested" / "repo" / "message.txt").write_text(AGENT)
        for command in (
            "git -C nested/repo commit -F message.txt",
            "git -Cnested -Crepo commit --file=message.txt",
            "cd nested/repo && git commit -Fmessage.txt",
            "cd nested; cd repo; git commit --template message.txt",
            "git -C nested/repo commit -tmessage.txt",
            "git commit -F " + shlex.quote(str(self.cwd / "nested/repo/message.txt")),
        ):
            with self.subTest(command=command):
                self.check(command, 2)
        self.check("git commit -F message.txt", 0)
        self.check("git -C nested/repo commit -F ../../message.txt", 0)

    def test_gh_write_messages(self):
        for resource, action in (
            ("pr", "create"), ("pr", "edit"), ("pr", "comment"),
            ("pr", "review"), ("issue", "create"), ("issue", "edit"),
            ("issue", "comment"),
        ):
            for option in ("--body ", "--body=", "-b ", "-b"):
                with self.subTest(resource=resource, action=action, option=option):
                    prefix = f"gh {resource} {action} "
                    self.check(prefix + option + shlex.quote(FOOTER), 2)
                    self.check(prefix + option + shlex.quote(HUMAN), 0)
        self.check("gh -R jfi/dotfiles pr create --title " + shlex.quote(FOOTER), 2)
        self.check("gh --repo=jfi/dotfiles pr edit 42 -t " + shlex.quote(FOOTER), 2)
        self.check("gh pr create --body https://claude.com/claude-code", 2)

    def test_gh_body_files(self):
        (self.cwd / "body with spaces.md").write_text(FOOTER)
        for option in ("--body-file ", "--body-file=", "-F ", "-F"):
            with self.subTest(option=option):
                self.check("gh pr create --title Update " + option + "'body with spaces.md'", 2)
        (self.cwd / "nested" / "repo" / "body.md").write_text(HUMAN)
        self.check("cd nested/repo && gh issue edit 12 --body-file body.md", 0)

    def test_read_only_and_unsubmitted_text(self):
        for command in (
            "gh pr list --search 'Generated with Claude Code'",
            "gh issue list --search 'co-authored-by: claude'",
            "gh pr view 12 --json body | grep -i 'co-authored-by: claude'",
            "gh issue view 12 | grep 'Generated with Claude Code'",
            "git log --grep='Generated with Claude Code'",
            "echo 'git commit -m Generated with Claude Code'",
            "gh pr create --body Clean && echo 'Generated with Claude Code'",
            "git commit -m Clean; echo 'co-authored-by: claude'",
            "gh pr create --body Clean --label 'Generated with Claude Code'",
            "gh pr view 12 --body-file missing.md",
        ):
            with self.subTest(command=command):
                self.check(command, 0)

    def test_write_in_compound_commands(self):
        for separator in (" && ", "; ", "\n", ";\n"):
            self.check("echo Ready" + separator + "git commit -m " + shlex.quote(AGENT), 2)
        self.check("FLAG=1 git commit -m " + shlex.quote(AGENT), 2)

    def test_comments_keep_command_boundaries(self):
        self.check("git add . # stage\ngit commit -m " + shlex.quote(AGENT), 2)
        self.check("# git commit -m " + shlex.quote(AGENT) + "\ngit status", 0)
        self.check("git commit -m '# Title'", 0)

    def test_heredocs_with_unmatched_quotes(self):
        self.check("cat <<'EOF' > notes.txt\nit's fine\nEOF\ngit status", 0)
        self.check("cat <<-EOF\n\tdon't\n\tEOF\ngit status", 0)
        message = "$(cat <<'EOF'\nFix it\n\n" + AGENT.split("\n\n")[1] + "\nEOF\n)"
        self.check('git commit -m "' + message + '"', 2)
        self.check('git commit -m "$(cat <<\'EOF\'\nFix it\nEOF\n)"', 0)

    def test_bundled_short_options(self):
        for command in (
            "git commit -am " + shlex.quote(AGENT),
            "git commit -sm" + shlex.quote(AGENT),
            "gh pr create -tx -b" + shlex.quote(FOOTER),
        ):
            with self.subTest(command=command):
                self.check(command, 2)
        (self.cwd / "m.txt").write_text(HUMAN)
        self.check("git commit -Fm.txt", 0)
        self.check("git commit -am " + shlex.quote(HUMAN), 0)

    def test_merge_and_close_messages(self):
        for command in (
            "gh pr merge 3 --body ", "gh pr merge 3 --subject ", "gh pr merge 3 -b ",
            "gh pr close 3 --comment ", "gh issue close 3 -c ",
        ):
            with self.subTest(command=command):
                self.check(command + shlex.quote(FOOTER), 2)
                self.check(command + "Clean", 0)

    def test_git_trailers(self):
        trailer = "Co-authored-by: Claude <noreply@anthropic.com>"
        self.check("git commit -m Fix --trailer " + shlex.quote(trailer), 2)
        self.check("git commit -m Fix --trailer=" + shlex.quote(trailer), 2)
        self.check("git commit -m Fix --trailer 'Co-authored-by=Claude'", 2)
        self.check("git commit -m Fix --trailer " + shlex.quote("Co-authored-by: jfi <j@example.com>"), 0)

    def test_unreadable_or_stdin_message_does_not_silently_pass(self):
        for path in ("-", "/dev/stdin", "/dev/fd/0", "/proc/self/fd/0", "/dev//stdin"):
            self.check("git commit -F " + path, 2)
            self.check("gh pr create --body-file " + path, 2)
        self.check("git commit -F missing.txt", 2)

    def test_empty_event(self):
        self.check("", 0)


if __name__ == "__main__":
    unittest.main()
