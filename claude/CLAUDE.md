# Global Claude Instructions

## Safety Rules

Claude runs with `--dangerously-skip-permissions`. Before executing any of
these commands, **always ask for confirmation**:

- `rm` or `rm -rf` (file/directory deletion)
- `git reset --hard`
- `git clean`
- `git checkout` that would discard changes
- `git stash drop` or `git stash clear`
- Any command with `--force` or `-f` that could lose data

## General Rules

- Never push to GitHub with `Gemfile`s which reference a path.
- When we update `version.rb` in any project, we need to also run a `bundle update --all`.
- Always run `bundle update --all` before committing changes.
- Add to memory that when a new command or agent is created, it should be
  committed and pushed inside `~/.claude`.
- For all gems I create unless I say otherwise: author to "Otaina Limited",
  "James Inman" and the email to "<james@otaina.co.uk>".
- Monitor PRs once you've pushed them for failures.
- You can browse the web as much as you need to. Let me know if you need me to
  bring in permissions to let you do this.
- If you need to connect to Rubygems, wait for OTP input.
- Don't push things to main branches - create PRs.
- If you're waiting for 1Password (e.g. unlocking the keychain), wait for me rather than trying to bypass
  or push unsigned commits.
