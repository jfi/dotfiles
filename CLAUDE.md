# Dotfiles Repository

macOS dotfiles.

## Structure

- `setup/` - Bootstrap scripts (run by `install` in order: `init`, `bootstrap`, `install-ruby`), plus optional `macos-defaults`
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
