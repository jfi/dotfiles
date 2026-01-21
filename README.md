# Dotfiles

Opinionated, minimal dotfiles for long-lived SSH work across macOS and Debian/Linux, with:

- **tmux-first workflow** (sessions = projects)
- **environment-aware titles** (Tabby / terminal titles reflect host, project, env)
- **Git SSH signing via 1Password**
- **Shared config with per-OS overrides**
- **Zero secrets committed**

This setup is designed to work equally well on:

- a local macOS laptop
- a remote Linux VPS
- long-running tmux sessions you attach/detach from frequently

---

## Server hardening (recommended)

This setup assumes you are running on a **reasonably hardened machine**, especially for remote Linux servers.

Before running `setup` on a VPS, you should have completed basic server hardening, including:

- SSH key-based authentication only
- Password login disabled
- Root login disabled
- Firewall enabled (SSH only, plus any required services)
- Regular security updates enabled
- A non-root user with `sudo`

This repository **does not automate hardening** by default — that is intentional.
Hardening scripts are highly context-dependent and easy to get wrong.

If you haven't done this yet, see [docs/server-hardening.md](docs/server-hardening.md) for a safe, manual checklist.

---

## One-line install

> ⚠️ This will overwrite `~/.zshrc`, `~/.zprofile`, `~/.tmux.conf`, and `~/.gitconfig`.

```bash
curl -fsSL https://raw.githubusercontent.com/jfi/dotfiles/main/install | bash
```

The installer is interactive on first run and will:

- prompt for your Git name & email
- guide you through selecting your SSH signing key from 1Password (macOS)
- write only **machine-local** data to `~/.dotfiles/.env` (git-ignored)

You can re-run it safely at any time.

---

## What this gives you

### tmux

- One **session per project**
- Automatic window renaming based on directory
- Titles like:

```text
hub • 🟥 prod • myapp • api
```

- Status bar shows environment (`DEV / STG / PROD`)
- Designed for long-lived SSH sessions

### Terminal / Tabby integration

- tmux controls the terminal title
- Tabby tabs update automatically
- Clear visual distinction between environments

### Git

- SSH commit signing (via 1Password on macOS)
- `allowed_signers` generated automatically
- Shared git config + per-OS config
- No private keys or secrets in the repo

### Shell

- Thin `~/.zshrc` loader
- Shared + OS-specific config files
- Works cleanly across macOS and Linux

### Setup scripts

Scripts run in numbered order: `1-*` first, then `2-*` (OS-specific), then `3-*`.

**`setup/1-init`**

- runs first on all platforms
- safe to run repeatedly
- does not install packages
- wires:
  - `~/.zshrc` + `~/.zprofile` loaders
  - `~/.tmux.conf` loader
  - `~/.gitconfig` includes
  - 1Password `allowed_signers` + `user.signingkey` on macOS

**`setup/2-bootstrap-macos`** / **`setup/2-bootstrap-debian`**

- OS-specific package installation
- runs `brew bundle` or `apt install` respectively
- installs mise and dependencies

**`setup/3-install-ruby`**

- runs on all platforms after OS bootstrap
- installs latest stable Ruby via mise
- updates RubyGems to latest version
- installs latest Bundler

### macOS extras

**`macos/defaults`**

- applies macOS system preferences tweaks
- see `macos/defaults.md` for documentation

---

## Repo layout

```text
.dotfiles/
├── install                   # one-line installer (curl entry point)
├── .env                      # local-only config (gitignored)
├── setup/
│   ├── 1-init                # main bootstrap script (runs first)
│   ├── 2-bootstrap-macos     # macOS package installation
│   ├── 2-bootstrap-debian    # Debian package installation
│   └── 3-install-ruby        # Ruby/mise setup (runs last)
├── macos/
│   ├── Brewfile              # Homebrew dependencies
│   ├── defaults              # macOS system preferences
│   └── defaults.md           # defaults documentation
├── git/
│   ├── gitconfig.shared
│   ├── gitconfig.macos
│   └── gitconfig.debian
├── tmux/
│   └── tmux.conf.shared
├── zsh/
│   ├── zshrc.shared
│   ├── zshrc.macos
│   ├── zshrc.debian
│   ├── zprofile.shared
│   ├── zprofile.macos
│   └── zprofile.debian
└── bin/
    ├── proj                  # project launcher
    └── with-ai-env           # AI environment wrapper
```

---

## Project workflow

```bash
proj myapp
```

- creates (or attaches to) a tmux session named `myapp`
- starts in `~/Projects/myapp`
- window names follow directories automatically

With environment set:

```bash
RAILS_ENV=production proj myapp
```

→ tmux + Tabby clearly show **PROD**

---

## Environment awareness

Environment is inferred from shell state and mirrored into tmux:

- `RAILS_ENV=production` → 🟥 PROD
- `RAILS_ENV=staging` → 🟧 STG
- unset / development → DEV

This affects:

- terminal / Tabby title
- tmux status bar

No guessing from hostnames.

---

## Secrets & safety

- No secrets committed
- All sensitive values live in:
  - `1Password`
  - `~/.dotfiles/.env` (git-ignored)
- Public SSH keys **are safe to commit**
- Private keys never leave 1Password

---

## Requirements

### macOS

- zsh (default)
- tmux
- 1Password + `op` CLI
- Python 3 (for setup wizard)

### Linux (Debian/Ubuntu)

- zsh
- tmux
- Python 3
- Optional: `fzf`

---

## Re-running setup

You can safely re-run:

```bash
~/.dotfiles/setup/1-init
```

It will:

- reuse values from `.env`
- only prompt if something is missing
- regenerate config files deterministically

---

## Philosophy

- tmux is the source of truth
- projects > machines
- explicit environment signalling
- boring, predictable shell config
- no magic that breaks under SSH

---

## Licence and contributing

MIT. Contributions appreciated.
