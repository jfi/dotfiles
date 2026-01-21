# Agent Guidelines

## Before Committing

Always run `lefthook run pre-commit` before committing to ensure:

- Markdown files pass linting (markdownlint-cli2)
- YAML files pass linting (yamllint)
- Shell scripts pass linting (shellcheck)

If lefthook is not installed, install it with `brew install lefthook` (macOS) or check the Brewfile for dependencies.
