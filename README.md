# Dotfiles

Personal macOS dotfiles, with:

- **Git SSH signing via 1Password**
- **Brewfile-managed packages and apps**, including the official Homebrew GUI
- **Repeatable configuration setup with backups**
- **Zero secrets committed**

---

## One-line install

> Review the Brewfile and setup scripts first. The full installer installs
> software, changes system preferences and requests administrator access.
> Replaced shell/config files are backed up under
> `~/.local/state/dotfiles/backups/`; existing Git configuration is preserved.

```bash
curl -fsSL https://raw.githubusercontent.com/jfi/dotfiles/main/install | bash
```

Run from a terminal. The installer is interactive on first run and will:

- require FileVault and install Command Line Tools if missing (then stop so you
  can complete Apple's dialog and rerun)
- discover or install Homebrew on Apple Silicon or Intel
- install Python, fzf and the 1Password CLI before the signing-key wizard
- clone over HTTPS, without needing an SSH key first
- prompt for your Git name & email
- guide you through selecting your SSH signing key from 1Password
- prompt for a computer name (used by `scutil`)
- write only **machine-local** data to `~/.dotfiles/.env` (git-ignored)

The clone is never automatically pulled or reset. For an existing checkout, run
`./install` to use its current scripts. Use `setup/init` alone when you only want
to refresh configuration; the full installer also reapplies macOS preferences.

---

## What this gives you

### Git

- SSH commit signing via 1Password
- `allowed_signers` generated automatically
- No private keys or secrets in the repo

### Touch ID for sudo

- Enables `pam_tid.so` using Apple's `/etc/pam.d/sudo_local.template`
- Bootstrap preserves an existing `/etc/pam.d/sudo_local` and does not edit the
  main PAM file
- Touch ID prompt appears instead of password

### Shell

- Thin `~/.zshrc` loader sources `zsh/zshrc` from the repo
- `~/.zshrc.local` for machine-specific additions (never overwritten by setup)
- `~/.zprofile.local` for machine-specific login-shell additions
- Homebrew paths work with `/opt/homebrew` or `/usr/local`; no fixed username
- starship prompt, atuin history, zoxide cd, eza/bat aliases, zsh-syntax-highlighting + zsh-autosuggestions

### Agent instructions

`claude/AGENTS.md` is the single global instruction file for coding agents.
`setup/init` symlinks it to `~/.claude/AGENTS.md` and `~/.codex/AGENTS.md`
(Codex), and `bin/agents-sync` writes two plain copies of it:

- `~/.claude/CLAUDE.md` for Claude Code and Cowork, because Cowork ignores a
  symlinked user-level `CLAUDE.md`
- `cursor/user-rules.md` for Cursor, which has no global instruction file;
  `pbcopy < cursor/user-rules.md` and paste into Cursor Settings > Rules > User
  Rules, then re-paste whenever it changes. Cursor Cloud agents only read a
  repo's own `AGENTS.md`, never this one.

The hk pre-commit hook regenerates both copies whenever `claude/AGENTS.md` is
committed; run `agents-sync` by hand after pulling, and `check-baseline` reports
drift. Edit `claude/AGENTS.md` only, never a copy.

Claude Code's `permissions.ask` rules in `claude/settings.json` are the
enforced counterpart of the Safety Rules section. Cowork, Codex and Cursor don't
read that file, so the prose list is the fallback there.

### Setup scripts

`install` runs the four in this order: `init`, `bootstrap`, `install-ruby`, `macos-defaults`.

**`setup/init`**

- runs first, safe to re-run
- does not install packages
- backs up files/symlinks before replacing them, including shadowing Ghostty files
- leaves SSH host policies alone; agent forwarding is not enabled globally
- wires:
  - `~/.zshrc` + `~/.zprofile` loaders
  - `~/.gitconfig` include
  - 1Password `allowed_signers` + `user.signingkey`
  - `~/.claude/AGENTS.md`, `~/.codex/AGENTS.md`,
    `~/.config/zed/{settings,keymap}.json`, `~/.config/ghostty/config` symlinks
  - `~/.claude/CLAUDE.md` as a copy (via `bin/agents-sync`)
  - hk git hooks
- seeds missing mise, Atuin and Claude settings from portable templates, without
  overwriting existing settings, trust paths or account state

**`setup/bootstrap`**

- runs `brew bundle install --no-upgrade` against `Brewfile` (dependencies may
  still be upgraded if an installation requires it)
- installs hk hooks after hk is available on a new Mac
- enables Touch ID for `sudo`
- enables the macOS Application Firewall
- runs `mise install` from the home directory, not the caller's project
- selects Node 24 LTS for Firebase's supported runtime, independently of
  Homebrew's newer Node dependency

**`setup/install-ruby`**

- installs the configured global Ruby via mise, without changing project versions
- new machines get Ruby 4.0.7 (newest stable checked on 5 October 2026) and
  `ruby.compile=false` from `mise/global.toml`; existing mise config is preserved
- updates RubyGems + installs latest Bundler

**`setup/macos-defaults`**

- applies macOS system preferences tweaks (Dock layout + pins, Finder/Safari/Activity
  Monitor defaults, screen-lock-on-sleep, Calendar notifications off,
  Spotlight Cmd-Space freed for Raycast, computer name)
- prompts for the computer name on first run; persists to `.env`
- does not trace `.env` values to the terminal
- also invokes the upstream pam-watchid installer for Apple Watch authentication;
  review this privileged integration before enabling it on another machine
- ends with a checklist of TCC permissions (Screen Recording, Accessibility,
  Full Disk Access, Input Monitoring) you need to grant manually in System Settings

---

## Repo layout

```text
.dotfiles/
|-- install                   # one-line installer (curl entry point)
|-- Brewfile                  # Homebrew dependencies
|-- hk.pkl                    # git hook config (hk)
|-- .env                      # local-only config (gitignored)
|-- setup/
|   |-- init                  # configuration setup (runs first)
|   |-- bootstrap             # packages, Touch ID for sudo, firewall
|   |-- install-ruby          # Ruby/mise setup
|   `-- macos-defaults        # macOS preferences + computer name
|-- git/                      # shared Git config and ignores
|-- zsh/                      # shared zshrc and zprofile
|-- claude/                   # global agent instructions + Claude defaults
|-- cursor/                   # generated copy of AGENTS.md for Cursor User Rules
|-- mise/global.toml          # portable global tools, copied only when missing
|-- atuin/config.toml         # history UI/sync preferences, never history data
|-- zed/                      # Zed settings + keymap
|-- ghostty/                  # Ghostty config
|-- k9s/                      # Rails console plugin
|-- tests/                    # isolated setup and document-scanning tests
`-- bin/
    |-- app-audit             # finds installed apps missing from Brewfile/README
    |-- brewfile-sync         # interactive Brewfile <-> install reconciler
    |-- check-baseline        # workstation health check
    |-- claude                # Claude Code wrapper
    |-- label                 # address label PDF (Ruby/Prawn), -p prints
    |-- munbyn-p44s           # Munbyn P44S label printer driver + CUPS queue
    |-- scan-documents        # document scanning (see docs/scanning.md)
    |-- agents-sync           # regenerates the AGENTS.md copies (Claude, Cursor)
    `-- with-ai-env           # 1Password-sourced AI env exec wrapper
```

---

## Secrets & safety

- No secrets committed
- Keep credentials in 1Password or application-managed local credential stores
- `.env` is git-ignored and written with mode 0600; do not copy it between Macs
- Shell account configuration belongs in `~/.zshrc.local` / `~/.zprofile.local`
- AWS/SSO profiles, SSH hosts, MCP credentials, mise trust paths, histories,
  application sessions and synchronised agent skills are not copied into Git
- Public SSH keys **are safe to commit**
- Only the public signing key is saved into Git configuration

---

## Requirements

- Target: Apple Silicon, macOS 26 or later. BrewUI (`homebrew-app`) requires 26+.
- FileVault, an administrator account, internet access and an interactive terminal.
- The installer provisions Homebrew, Python, fzf and 1Password. Sign in to
  1Password and enable CLI integration and its SSH agent when prompted.
- Sign in to the App Store and acquire any paid apps before `brew bundle`.
- Microsoft ODBC tools may require accepting their licence during installation.
- Intel paths are supported by the scripts, but Homebrew 7 places Intel in Tier 3
  with no new routine bottles. Some casks are architecture-specific; the complete
  manifest is not guaranteed to install on Intel or older macOS versions.

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
- preserve `.zshrc.local`, `.zprofile.local`, personal Git configuration and
  existing mise, Atuin and Claude settings
- keep replaced files in `~/.local/state/dotfiles/backups/` for manual recovery

The full installer is not a dry run. `setup/macos-defaults` changes the Dock,
system preferences and authentication integration; review it before running on
an established machine. Some preference writes need Full Disk Access and are
best-effort. App logins, licences, TCC permissions and hardware pairing remain
manual steps.

---

## Manual installs

Items kept outside `Brewfile`. Install or restore only what this Mac needs:

- **Amp** - install the native app from <https://ampcode.com/docs/macos-and-ios>.
  For the CLI, use `curl -fsSL https://ampcode.com/install.sh | bash`, then sign in.
  The shared shell already includes `~/.amp/bin` and `~/.local/bin`.
- **Local CLIs and skills** - Rafiki also has manually installed Sentry, Notion
  (`ntn`) and Plannotator CLIs, plus agent skills managed outside this repository.
  Reinstall them from their upstream instructions as needed; do not copy binaries,
  authenticated settings or skill caches into dotfiles.
- **Work and hardware software** - restore company-managed VPN, Drata and printer
  software through their managed installers. TestFlight apps such as Lettera
  require their invitation/account, not a reusable App Store ID.
- **Sonos** - download from sonos.com. A `cask "sonos"` does exist
  (`brew install --cask sonos`), but it's Intel-only and requires Rosetta 2
  ("very difficult to remove once installed", per the cask's own caveat), so
  it's kept manual to avoid that dependency.
- **UniFi** - download from ui.com. No Homebrew cask exists for the UniFi
  Network application (only the self-hosted controller, which is separate).
- **Munbyn P44S label printer** - no cask, and the vendor driver is a plain
  `.pkg` (a CUPS PPD plus a TSPL raster filter, x86_64 only, so Rosetta 2).
  Run `munbyn-p44s <printer-ip>` (or `munbyn-p44s usb`): it downloads and
  checksums the driver, disables the vendor's root LaunchDaemon and adds the
  `Munbyn_P44S` queue over a raw socket. Join the printer to Wi-Fi first with
  the Munbyn Print phone app (Bluetooth pairing PIN `0000`), then take its IP
  from the router's client list. Bluetooth from macOS is not a supported path
  for this model, and it speaks TSPL, not ZPL. `label "Name" "Street" "Town"`
  renders a 6 x 4 in address label to PDF, sideways on the 4 x 6 in page as
  the printer feeds it and with room for a stamp, and `label -p` prints it.

---

## Syncing between machines

Install something via `brew install` / `brew install --cask` / `mas install` on one
machine and want it on the next? Run:

```bash
brewfile-sync
```

It diffs the live install against `Brewfile`, walks every difference
interactively (y/n/q per line for both adds and drops), writes the result
back, and offers to stage + commit. It compares package names and App Store IDs,
so trust flags and renamed MAS display names do not create duplicate installs.
Review changes on a branch and use a PR; then run `brew bundle` on the other Mac.

`brewfile-sync` only knows about `tap`/`brew`/`cask`/`mas` entries though - it cannot
see apps that were dragged into `/Applications` by hand or left behind by an
installer. For that, run:

```bash
app-audit
```

It cross-references every installed app (and MAS app) against the Brewfile
and the "Manual installs" list above, and reports anything untracked -
either add it to `Brewfile`/README, or trash it if it's cruft.

The Brewfile is the desired new-Mac install list, not a dump of every historical
app on Rafiki. Do not run `brew bundle cleanup` as part of this review: it would
uninstall packages and is deliberately not part of setup.

## October 2026 cleanup

Reviewed on 5 October against installed Homebrew/MAS receipts, current app
processes, Spotlight last-used dates and command-name-only history counts for
the preceding three weeks (706 records since 14 September). No raw history or
credentials were copied.

Removed only these six app install entries after reviewing old recorded launches
and checking that none were running: GitHub Desktop (2 July), Twilight (22 June),
NotePlan (11 June), SnippetsLab (15 May), Moonlight (17 August) and Taphouse
(15 June). This is medium-confidence usage evidence, not proof of disuse; the
owner approved dropping them. No apps or personal data were deleted. BrewUI is
the replacement package-management GUI.

Also removed duplicate tap/package declarations, duplicate Canva/Cardhop/Spark
App Store routes, the obsolete Canary Mail entry (previously replaced by Spark),
and the stable 1Password CLI entry (explicitly uninstalled on 4 October in favour
of the installed beta). The absent Python 3.13 pin is replaced by Homebrew's
current Python. The stale Spark CLI symlink is no longer created.

Retained background tools including OrbStack, Rectangle Pro, Espanso and
Tailscale; running processes or LaunchAgents contradict their old launch dates.
Recovery tools, database versions, fonts and apps with missing/ambiguous usage
evidence remain. `brewfile-sync` may offer to re-add intentionally pruned apps
because they are still installed here; decline those additions.

## Verification

```bash
python3 -m unittest discover -s tests -p test_setup.py -v
hk run pre-commit --all --check --stash none
zsh -n zsh/zprofile && zsh -n zsh/zshrc
brew bundle check --no-upgrade --verbose --file=Brewfile
```

Setup tests use macOS system Bash, a disposable home (including a space in its
path), fake package/authentication commands and a pseudo-terminal for the
installer. They verify backups, repeated runs, local settings, package identity
comparison and dependency ordering without installing software or using sudo.
The macOS CI job runs the same tests. Scanner tests are documented in
[docs/scanning.md](docs/scanning.md).

`brew bundle check` is read-only and may report missing receipts for apps
installed directly or intentionally retained packages. It does not prove a
clean-Mac install. Actual downloads, 1Password sign-in, App Store purchases,
administrator changes and Intel hardware still need an on-device setup trial.

---

## Licence and contributing

MIT. Contributions appreciated.
