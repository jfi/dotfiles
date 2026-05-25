# Agent Guidelines

macOS dotfiles.

## Structure

- `setup/` - Bootstrap scripts (run by `install` in order: `init`, `bootstrap`,
  `macos-defaults`, `install-ruby`)
- `bin/` - User commands (added to PATH)
- `zsh/` - Shell configuration
- `tmux/` - tmux configuration
- `git/` - Git configuration + global gitignore
- `Brewfile` - Homebrew dependencies (at repo root, brew's default lookup)
- `hk.pkl` - git hook runner config (hk)
- `.config/` - Linter configs (yamllint, markdownlint)

## Guidelines

- Shell scripts must pass ShellCheck
- Don't push to main directly - create PRs

## Before Committing

Always run `hk run pre-commit` before committing to ensure:

- Markdown files pass linting (markdownlint-cli2)
- YAML files pass linting (yamllint)
- Shell scripts pass linting (shellcheck)
- No git conflict markers are present

If hk is not installed, install it with `brew install hk` (it's in `Brewfile`).
