"""Setup regression tests with a disposable HOME and no network or sudo."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dotfiles-test-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "new user"
        self.home.mkdir()
        self.repo = self.home / ".dotfiles"
        self.repo.mkdir()
        for name in ("setup", "bin", "zsh", "git", "claude", "cursor", "zed", "ghostty", "k9s"):
            shutil.copytree(ROOT / name, self.repo / name)
        for name in ("mise", "atuin"):
            if (ROOT / name).exists():
                shutil.copytree(ROOT / name, self.repo / name)
        self.commands = self.home / "commands"
        self.commands.mkdir()
        (self.commands / "python3").symlink_to(sys.executable)
        self.stub("hk", 'printf "%s\\n" "$*" >> "$HOME/hk-calls"')
        # Guard against accidental live side effects, including old deletion code.
        for cmd in ("sudo", "curl", "rm"):
            self.stub(cmd, 'echo "Unexpected side effect" >&2; exit 90')
        self.env = {
            "HOME": str(self.home),
            "TMPDIR": str(self.home),
            "PATH": f"{self.commands}:/usr/bin:/bin:/usr/sbin:/sbin",
            "DOTFILES_GIT_NAME": 'New "User" $HOME',
            "DOTFILES_GIT_EMAIL": "new@example.test",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        self.stub("op", '''
case "$1 ${2:-}" in
  "whoami ") exit 0 ;;
  "vault list") echo '[{"name":"Test vault","id":"vault-id"}]' ;;
  "item list") echo '[{"title":"Signing key","id":"item-id"}]' ;;
  "item get") echo '{"fields":[{"id":"public_key","label":"Public key","value":"ssh-ed25519 AAAAtest"}]}' ;;
  *) exit 91 ;;
esac
''')
        self.stub("fzf", "head -1")

    def stub(self, name, body):
        path = self.commands / name
        path.write_text("#!/bin/bash\nset -eu\n" + body + "\n", encoding="ascii")
        path.chmod(0o755)

    def run_init(self):
        result = subprocess.run(
            ["/bin/bash", str(self.repo / "setup/init")],
            cwd=self.home, env=self.env, input="", text=True, capture_output=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def git_config(self, key):
        return subprocess.check_output(
            ["git", "config", "--global", "--includes", "--get", key],
            cwd=self.home, env=self.env, text=True,
        ).strip()

    def test_first_run_works_with_system_bash_and_preserves_existing_files(self):
        original = self.home / "original-shell"
        original.write_text("# personal shell settings\n")
        (self.home / ".zshrc").symlink_to(original)
        (self.home / ".zshrc.local").write_text("# local override\n")
        (self.home / ".gitconfig").write_text(
            '[alias]\n  personal = status --short\n[core]\n  editor = personal-editor\n'
        )
        shadow = self.home / "Library/Application Support/com.mitchellh.ghostty/config"
        shadow.parent.mkdir(parents=True)
        shadow.write_text("font-size = 19\n")
        self.run_init()
        self.assertEqual(original.read_text(), "# personal shell settings\n")
        self.assertEqual((self.home / ".zshrc.local").read_text(), "# local override\n")
        self.assertEqual(self.git_config("alias.personal"), "status --short")
        self.assertEqual(self.git_config("core.editor"), "personal-editor")
        self.assertEqual(self.git_config("user.name"), self.env["DOTFILES_GIT_NAME"])
        self.assertEqual(self.git_config("user.signingkey"), "ssh-ed25519 AAAAtest")
        self.assertFalse(shadow.exists())
        backups = list((self.home / ".local/state/dotfiles/backups").rglob("config"))
        self.assertTrue(any(p.read_text() == "font-size = 19\n" for p in backups))
        self.assertFalse((self.home / ".ssh/config").exists())
        self.assertEqual((self.home / ".config/mise/config.toml").read_text(),
                         (ROOT / "mise/global.toml").read_text())
        self.assertEqual((self.home / ".config/atuin/config.toml").read_text(),
                         (ROOT / "atuin/config.toml").read_text())
        self.assertEqual((self.repo / ".env").stat().st_mode & 0o777, 0o600)
        env_result = subprocess.check_output(
            ["/bin/bash", "-c", 'source "$HOME/.dotfiles/.env"; printf "%s" "$DOTFILES_GIT_NAME"'],
            env=self.env, text=True,
        )
        self.assertEqual(env_result, self.env["DOTFILES_GIT_NAME"])

    def test_second_run_keeps_local_changes_and_does_not_multiply_backups(self):
        self.env.update(DOTFILES_OP_SIGNING_VAULT_ID="vault-id", DOTFILES_OP_SIGNING_ITEM_ID="item-id")
        (self.home / ".zshrc").write_text("# previous config\n")
        self.run_init()
        backups = list((self.home / ".local/state/dotfiles/backups").rglob("*"))
        (self.home / ".config/mise/config.toml").write_text('# local trust paths\n')
        (self.home / ".claude/settings.json").write_text('{"model":"local-choice"}\n')
        self.run_init()
        self.assertEqual((self.home / ".config/mise/config.toml").read_text(), '# local trust paths\n')
        self.assertEqual((self.home / ".claude/settings.json").read_text(), '{"model":"local-choice"}\n')
        self.assertEqual(backups, list((self.home / ".local/state/dotfiles/backups").rglob("*")))
        values = subprocess.check_output(
            ["git", "config", "--global", "--get-all", "include.path"],
            env=self.env, text=True,
        ).splitlines()
        self.assertEqual(values.count("~/.dotfiles/git/gitconfig"), 1)

    def test_zsh_uses_home_and_homebrew_prefix_without_clobbering_flags(self):
        prefix = self.home / "intel-brew"
        libxml = prefix / "opt/libxml2"
        libxml.mkdir(parents=True)
        plugins = prefix / "share/zsh-autosuggestions"
        plugins.mkdir(parents=True)
        (plugins / "zsh-autosuggestions.zsh").write_text("export TEST_PLUGIN=loaded\n")
        self.env.update(HOMEBREW_PREFIX=str(prefix), LDFLAGS="-L/custom", CPPFLAGS="-I/custom")
        result = subprocess.run(
            ["/bin/zsh", "-fc", 'source "$HOME/.dotfiles/zsh/zshrc"; '
             'print -r -- "$PATH" "$LDFLAGS" "$CPPFLAGS" "$TEST_PLUGIN"'],
            cwd=self.home, env=self.env, text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.home / ".amp/bin"), result.stdout)
        self.assertNotIn("/Users/james", result.stdout)
        self.assertIn(f"-L{libxml}/lib -L/custom", result.stdout)
        self.assertIn(f"-I{libxml}/include -I/custom", result.stdout)
        self.assertIn("loaded", result.stdout)

    def test_bootstrap_installs_without_upgrading_and_installs_hooks_after_brew(self):
        self.stub("brew", 'printf "%s\\n" "$*" >> "$HOME/brew-calls"')
        self.stub("sudo", '''
printf "%s\\n" "$*" >> "$HOME/sudo-calls"
case "$*" in
  *--getglobalstate*) echo 'Firewall is enabled. (State = 1)' ;;
esac
''')
        self.stub("mise", 'printf "%s\\n" "$*" >> "$HOME/mise-calls"')
        self.stub("gh", 'printf "%s\\n" "$*" >> "$HOME/gh-calls"')
        (self.home / ".gitconfig").write_text(
            "[credential]\n\thelper = \n\thelper = /usr/local/share/gcm-core/git-credential-manager\n"
            '[credential "https://dev.azure.com"]\n\tuseHttpPath = true\n')
        result = subprocess.run(
            ["/bin/bash", str(self.repo / "setup/bootstrap")],
            cwd=self.home, env=self.env, text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.home / "brew-calls").read_text().splitlines(),
                         [f"bundle install --verbose --no-upgrade --file={self.repo}/Brewfile",
                          "services start atuin"])
        self.assertEqual((self.home / "gh-calls").read_text(), "auth status --hostname github.com\n")
        self.assertEqual((self.home / "hk-calls").read_text(), "install\n")
        gitconfig = (self.home / ".gitconfig").read_text()
        self.assertNotIn("git-credential-manager", gitconfig)
        self.assertIn("useHttpPath = true", gitconfig)
        self.assertNotIn("Spark", (self.home / "sudo-calls").read_text())
        self.assertNotIn("doctor", (self.home / "mise-calls").read_text())

    def test_bootstrap_installs_gh_before_brew_bundle_and_warns_when_signed_out(self):
        gh = self.commands / "gh"
        self.stub("brew", f'''
printf "%s\\n" "$*" >> "$HOME/brew-calls"
if [ "$*" = "install gh" ]; then
  printf '#!/bin/bash\\nprintf "%%s\\\\n" "$*" >> "$HOME/gh-calls"\\nexit 1\\n' > "{gh}"
  chmod +x "{gh}"
fi
''')
        self.stub("sudo", "echo 'Firewall is enabled. (State = 1)'")
        self.stub("mise", "true")
        result = subprocess.run(
            ["/bin/bash", str(self.repo / "setup/bootstrap")],
            cwd=self.home, env=self.env, text=True, capture_output=True, timeout=15,
            stdin=subprocess.DEVNULL,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.home / "brew-calls").read_text().splitlines(),
                         ["install gh",
                          f"bundle install --verbose --no-upgrade --file={self.repo}/Brewfile",
                          "services start atuin"])
        self.assertEqual((self.home / "gh-calls").read_text(), "auth status --hostname github.com\n")
        self.assertIn("gh auth login", result.stderr)

    def test_ruby_setup_keeps_the_configured_version_instead_of_selecting_latest(self):
        self.stub("mise", '''
printf "%s\\n" "$*" >> "$HOME/mise-calls"
if [ "$1" = ls-remote ]; then printf '3.3.0\\n9.9.9\\n'; fi
''')
        result = subprocess.run(
            ["/bin/bash", str(self.repo / "setup/install-ruby")],
            cwd=self.home, env=self.env, text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = (self.home / "mise-calls").read_text()
        self.assertNotIn("ls-remote", calls)
        self.assertNotIn("use --global", calls)
        self.assertIn("install ruby", calls)

    @unittest.skipUnless(sys.platform == "darwin", "macOS script(1) syntax")
    def test_installer_uses_https_and_installs_wizard_dependencies_first(self):
        self.stub("fdesetup", "echo 'FileVault is On.'")
        self.stub("xcode-select", "echo /Library/Developer/CommandLineTools")
        self.stub("brew", '''
printf "%s\\n" "$*" >> "$HOME/install-calls"
if [ "$1" = shellenv ]; then echo 'export HOMEBREW_PREFIX=/usr/local'; fi
if [ "$*" = "list --formula python" ]; then exit 1; fi
''')
        self.stub("git", '''
printf "%s\\n" "$*" >> "$HOME/install-calls"
if [ "$1" = clone ]; then cp -R "$HOME/prepared" "$3"; fi
''')
        for name in ("init", "bootstrap", "install-ruby", "macos-defaults"):
            path = self.repo / "setup" / name
            path.write_text(f'#!/bin/bash\nprintf "{name}\\n" >> "$HOME/install-calls"\n')
        self.repo.rename(self.home / "prepared")
        result = subprocess.run(
            ["/usr/bin/script", "-q", "/dev/null", "/bin/bash", str(ROOT / "install")],
            cwd=self.home, env=self.env, input="", text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = (self.home / "install-calls").read_text().splitlines()
        self.assertIn(f"clone https://github.com/jfi/dotfiles.git {self.repo}", calls)
        self.assertLess(calls.index("install python"), calls.index("init"))
        self.assertNotIn("install python fzf", calls)
        self.assertEqual(calls[-4:], ["init", "bootstrap", "install-ruby", "macos-defaults"])

    def test_claude_wrapper_finds_homebrew_binary(self):
        prefix = self.home / "homebrew"
        (prefix / "bin").mkdir(parents=True)
        self.stub("claude", 'printf "%s\\n" "$@"')
        (prefix / "bin/claude").symlink_to(self.commands / "claude")
        self.env["HOMEBREW_PREFIX"] = str(prefix)
        result = subprocess.run(
            ["/bin/bash", str(self.repo / "bin/claude"), "--version"],
            env=self.env, text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "--dangerously-skip-permissions\n--version\n")

    def test_brewfile_sync_compares_identity_not_options_or_mas_display_names(self):
        # Cleanup belongs to TemporaryDirectory; do not run the script's rm.
        self.stub("rm", ":")
        (self.repo / "Brewfile").write_text(
            'tap "depot/tap", trusted: true\n'
            'brew "depot/tap/depot", trusted: true\n'
            'mas "Numbers Creator Studio", id: 361304891\n'
        )
        self.stub("brew", '''
for arg in "$@"; do
  case "$arg" in
    --file=*) printf 'tap "depot/tap"\\nbrew "depot/tap/depot"\\nmas "Numbers", id: 361304891\\n' > "${arg#--file=}" ;;
  esac
done
''')
        result = subprocess.run(
            ["/bin/bash", str(self.repo / "bin/brewfile-sync")],
            env=self.env, text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Brewfile is in sync", result.stdout)

        # A truly new package and a removed one must still be distinguished.
        with (self.repo / "Brewfile").open("a") as manifest:
            manifest.write('cask "only-tracked", trusted: true\n')
        result = subprocess.run(
            ["/bin/bash", str(self.repo / "bin/brewfile-sync")],
            env=self.env, text=True, capture_output=True, timeout=15,
        )
        self.assertIn('- cask "only-tracked", trusted: true', result.stdout)
        self.assertNotIn("Brewfile is in sync", result.stdout)

    def test_macos_preferences_do_not_trace_local_env(self):
        (self.repo / ".env").write_text('LOCAL_SECRET="test-secret-must-not-be-logged"\n')
        # Run only the real loading preamble, before any OS preference writes.
        preamble = (self.repo / "setup/macos-defaults").read_text().split(
            "# Close open System Settings windows"
        )[0]
        result = subprocess.run(
            ["/bin/bash", "-c", preamble], env=self.env, text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("test-secret-must-not-be-logged", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
