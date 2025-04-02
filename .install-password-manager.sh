#!/bin/bash
set -ex

# Install XCode Command Line Tools if necessary
xcode-select --install || echo "XCode already installed"

# Install Homebrew if necessary
if which -s brew; then
    echo 'Homebrew is already installed'
else
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    (
        echo
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"'
    ) >>$HOME/.zprofile
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi

if type op >/dev/null 2>&1; then
    echo "1Password CLI is already installed"
else
    case "$(uname -s)" in
    Darwin)
        brew install --cask 1password
        brew install 1password-cli
        ;;
    *)
        echo "unsupported OS"
        exit 1
        ;;
    esac
fi

read -p "Please open 1Password, log into all accounts and under Settings > Developer activate the 1Password CLI and SSH Agent. Press any key to continue." -n 1 -r
echo
