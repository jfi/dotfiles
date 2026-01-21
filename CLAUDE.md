# Dotfiles Repository

Cross-platform dotfiles for macOS and Debian.

## Structure

- `setup/` - Bootstrap scripts (run in order: 1-init, 2-bootstrap, 3-install)
- `bin/` - User commands (added to PATH)
- `zsh/` - Shell configuration
- `tmux/` - tmux configuration
- `git/` - Git configuration
- `.config/` - Linter configs (lefthook, yamllint, markdownlint)

## Guidelines

- Shell scripts must pass ShellCheck
- Test changes on both macOS and Debian when possible
- Don't push to main directly - create PRs
