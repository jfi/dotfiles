# dotfiles

This uses [chezmoi](https://www.chezmoi.io) to manage dotfiles.

Some of this was heavily influenced by the following:

* https://github.com/mathiasbynens/dotfiles/

## Installation

First, install Homebrew and 1Password:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/jfi/dotfiles/refs/heads/main/install-password-manager.sh)"
```

Follow the instructions to configure 1Password, then run:

```bash
sh -c "$(curl -fsLS get.chezmoi.io)" -- init --apply jfi
```

You will be prompted for your admin password a few times throughout the installation process.

## Changing dotfiles

To show changes, run:

```
chezmoi diff
```

To apply changes, run:

```
chezmoi apply -v
```

To apply the changes from the remote, run:

```
chezmoi update -v
```

See [chezmoi documentation](https://www.chezmoi.io/quick-start/#using-chezmoi-across-multiple-machines) for more information.
