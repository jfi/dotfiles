# Dotfiles

Opinionated, minimal macOS dotfiles, with:

- **tmux-first workflow** (sessions = projects)
- **environment-aware titles** (Tabby / terminal titles reflect host, project, env)
- **Git SSH signing via 1Password**
- **Zero secrets committed**

Designed for long-running tmux sessions you attach/detach from frequently — locally and over SSH.

---

## One-line install

> ⚠️ This will overwrite `~/.zshrc`, `~/.zprofile`, `~/.tmux.conf`, and `~/.gitconfig`.

```bash
curl -fsSL https://raw.githubusercontent.com/jfi/dotfiles/main/install | bash
```

The installer is interactive on first run and will:

- prompt for your Git name & email
- guide you through selecting your SSH signing key from 1Password
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

- SSH commit signing via 1Password
- `allowed_signers` generated automatically
- No private keys or secrets in the repo

### Touch ID for sudo

- Enables `pam_tid.so` in `/etc/pam.d/sudo`
- Touch ID prompt appears instead of password

### Shell

- Thin `~/.zshrc` loader sources `zsh/zshrc` from the repo
- `~/.zshrc.local` for machine-specific additions (never overwritten by setup)

### Setup scripts

`install` runs the four in this order: `init`, `bootstrap`, `macos-defaults`, `install-ruby`.

**`setup/init`**

- runs first, safe to re-run
- does not install packages
- wires:
  - `~/.zshrc` + `~/.zprofile` loaders
  - `~/.tmux.conf` loader
  - `~/.gitconfig` include
  - 1Password `allowed_signers` + `user.signingkey`

**`setup/bootstrap`**

- runs `brew bundle` against `Brewfile`
- enables Touch ID for `sudo`
- enables the macOS Application Firewall
- runs `mise install`

**`setup/install-ruby`**

- installs latest stable Ruby via mise
- updates RubyGems to latest version
- installs latest Bundler

**`setup/macos-defaults`**

- applies macOS system preferences tweaks (Dock layout + pins,
  Finder/Safari/Activity Monitor defaults, screen-lock-on-sleep,
  Calendar notifications off, Spotlight Cmd-Space freed for Raycast,
  Touch-ID-for-sudo, computer name)
- prompts for the computer name on first run; persists to `.env`

---

## Repo layout

```text
.dotfiles/
├── install                   # one-line installer (curl entry point)
├── Brewfile                  # Homebrew dependencies
├── hk.pkl                    # git hook config (hk)
├── .env                      # local-only config (gitignored)
├── setup/
│   ├── init                  # main bootstrap script (runs first)
│   ├── bootstrap             # packages, Touch ID for sudo, firewall
│   ├── macos-defaults        # macOS system preferences + computer name
│   └── install-ruby          # Ruby/mise setup
├── git/
│   ├── gitconfig
│   └── gitignore
├── tmux/
│   └── tmux.conf
├── zsh/
│   ├── zshrc
│   └── zprofile
└── bin/
    ├── brewfile-sync         # interactive Brewfile <-> install reconciler
    ├── claude                # Claude Code wrapper (full permissions)
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

- macOS
- zsh (default)
- tmux
- 1Password + `op` CLI
- Python 3 (for setup wizard)

---

## Re-running setup

You can safely re-run:

```bash
~/.dotfiles/setup/init
```

It will:

- reuse values from `.env`
- only prompt if something is missing
- regenerate config files deterministically

---

## Syncing between machines

Install something via `brew install` / `brew install --cask` / `mas install` on one
machine and want it on the next? Run:

```bash
brewfile-sync
```

It diffs the live install against `Brewfile`, walks every difference
interactively (y/n/q per line for both adds and drops), and writes the
result back. Commit, push, run `brew bundle` on the other Mac.

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
