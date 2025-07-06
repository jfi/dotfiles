# dotfiles

This uses [chezmoi](https://www.chezmoi.io) to manage dotfiles.

Some of this was heavily influenced by the following:

* https://github.com/mathiasbynens/dotfiles/

## Installation

This hasn't been tested recently but:

```
sh -c "$(curl -fsLS get.chezmoi.io)" -- init --apply jfi
```

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
