# Dotfiles

Opinionated, minimal macOS dotfiles, with:

- **Git SSH signing via 1Password**
- **Brewfile-managed everything** (packages, casks, Mac App Store apps)
- **Idempotent setup scripts**
- **Zero secrets committed**

---

## One-line install

> ⚠️ This will overwrite `~/.zshrc`, `~/.zprofile`, and `~/.gitconfig`.

```bash
curl -fsSL https://raw.githubusercontent.com/jfi/dotfiles/main/install | bash
```

The installer is interactive on first run and will:

- prompt for your Git name & email
- guide you through selecting your SSH signing key from 1Password
- prompt for a computer name (used by `scutil`)
- write only **machine-local** data to `~/.dotfiles/.env` (git-ignored)

You can re-run it safely at any time.

---

## What this gives you

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
- starship prompt, atuin history, zoxide cd, eza/bat aliases, zsh-syntax-highlighting + zsh-autosuggestions

### Setup scripts

`install` runs the four in this order: `init`, `bootstrap`, `install-ruby`, `macos-defaults`.

**`setup/init`**

- runs first, safe to re-run
- does not install packages
- wires:
  - `~/.zshrc` + `~/.zprofile` loaders
  - `~/.gitconfig` include
  - 1Password `allowed_signers` + `user.signingkey`
  - `~/.claude/{CLAUDE,AGENTS}.md`, `~/.config/zed/{settings,keymap}.json`,
    `~/.config/ghostty/config` symlinks
  - hk git hooks

**`setup/bootstrap`**

- runs `brew bundle` against `Brewfile`
- enables Touch ID for `sudo`
- enables the macOS Application Firewall
- runs `mise install`

**`setup/install-ruby`**

- sets `mise settings ruby.compile=false` so Ruby installs from prebuilt binaries
- installs latest stable Ruby via mise
- updates RubyGems + installs latest Bundler

**`setup/macos-defaults`**

- applies macOS system preferences tweaks (Dock layout + pins, Finder/Safari/Activity
  Monitor defaults, screen-lock-on-sleep, Calendar notifications off,
  Spotlight Cmd-Space freed for Raycast, computer name)
- prompts for the computer name on first run; persists to `.env`
- ends with a checklist of TCC permissions (Screen Recording, Accessibility,
  Full Disk Access, Input Monitoring) you need to grant manually in System Settings

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
│   ├── install-ruby          # Ruby/mise setup
│   └── macos-defaults        # macOS system preferences + computer name
├── git/
│   ├── gitconfig
│   └── gitignore
├── zsh/
│   ├── zshrc
│   └── zprofile
├── claude/                   # global Claude / AGENTS instructions
├── zed/                      # Zed settings + keymap
├── ghostty/                  # Ghostty config
└── bin/
    ├── app-audit             # finds installed apps missing from Brewfile/README
    ├── brewfile-sync         # interactive Brewfile <-> install reconciler
    ├── check-baseline        # workstation health check
    ├── claude                # Claude Code wrapper
    └── with-ai-env           # 1Password-sourced AI env exec wrapper
```

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

## Manual installs

Things not in `Brewfile` because no Homebrew cask exists. Install once per
machine from the upstream site:

- **Sonos** — download from sonos.com. A `cask "sonos"` does exist
  (`brew install --cask sonos`), but it's Intel-only and requires Rosetta 2
  ("very difficult to remove once installed", per the cask's own caveat), so
  it's kept manual to avoid that dependency.
- **UniFi** — download from ui.com. No Homebrew cask exists for the UniFi
  Network application (only the self-hosted controller, which is separate).

---

## Syncing between machines

Install something via `brew install` / `brew install --cask` / `mas install` on one
machine and want it on the next? Run:

```bash
brewfile-sync
```

It diffs the live install against `Brewfile`, walks every difference
interactively (y/n/q per line for both adds and drops), writes the result
back, and offers to stage + commit. `git push`, then `brew bundle` on the
other Mac.

`brewfile-sync` only knows about `brew`/`cask`/`mas` entries though — it can't
see apps that were dragged into `/Applications` by hand or left behind by an
installer. For that, run:

```bash
app-audit
```

It cross-references every installed app (and MAS app) against the Brewfile
and the "Manual installs" list above, and reports anything untracked —
either add it to `Brewfile`/README, or trash it if it's cruft.

---

## Licence and contributing

MIT. Contributions appreciated.
