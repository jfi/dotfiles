# Agent Guidelines

## Before Committing

Always run `hk run pre-commit` before committing to ensure:

- Markdown files pass linting (markdownlint-cli2)
- YAML files pass linting (yamllint)
- Shell scripts pass linting (shellcheck)
- No git conflict markers are present

If hk is not installed, install it with `brew install hk` (it's in `Brewfile`).
