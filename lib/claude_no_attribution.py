"""Inspect literal shell arguments without evaluating shell code or expansions.

This is a guard for ordinary Git/gh invocations, not a shell interpreter. Dynamic
messages (command substitutions, stdin, etc.) cannot be fully inspected here.
"""

import json
from pathlib import Path
import re
import shlex
import sys


ATTRIBUTION = re.compile(
    r"co-authored-by:.*(?:claude|anthropic)|generated with.*claude code|"
    r"claude\.com/claude-code",
    re.IGNORECASE,
)


def commands(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    words = []
    for word in lexer:
        if word and all(character in ";&|()\n" for character in word):
            if words:
                yield words
            words = []
        else:
            words.append(word)
    if words:
        yield words


def option_values(arguments, long_names, short_names):
    """Yield literal values of message options, including attached forms."""
    index = 0
    while index < len(arguments):
        word = arguments[index]
        if word == "--":
            return
        if word in long_names or word in short_names:
            index += 1
            if index < len(arguments):
                yield arguments[index]
        elif any(word.startswith(name + "=") for name in long_names):
            yield word.split("=", 1)[1]
        elif any(word.startswith(name) and len(word) > 2 for name in short_names):
            yield word[2:]
        index += 1


def git_commit(words, cwd):
    """Skip Git's global options and apply each -C in order."""
    index = 1
    while index < len(words):
        word = words[index]
        if not word.startswith("-"):
            return (words[index + 1 :], cwd) if word == "commit" else (None, cwd)
        if word in {"-C", "-c", "--git-dir", "--work-tree", "--namespace",
                    "--config-env", "--super-prefix", "--exec-path"}:
            index += 1
            if index >= len(words):
                return None, cwd
            if word == "-C":
                cwd = cwd / words[index]
        elif word.startswith("-C"):
            cwd = cwd / word[2:]
        index += 1
    return None, cwd


def gh_write(words):
    index = 1
    while index < len(words) and words[index].startswith("-"):
        if words[index] in {"-R", "--repo", "--hostname"}:
            index += 1
        index += 1
    if index + 1 >= len(words):
        return None
    resource, action = words[index : index + 2]
    actions = {"create", "edit", "comment"}
    if resource == "pr":
        actions.add("review")
    if resource in {"pr", "issue"} and action in actions:
        return words[index + 2 :]
    return None


def inspect(command, cwd):
    for words in commands(command):
        # Shell assignment prefixes do not change the executable.
        while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
            words = words[1:]
        if not words:
            continue
        executable = Path(words[0]).name
        if executable == "cd" and len(words) == 2:
            cwd = cwd / words[1]
            continue
        message_cwd = cwd
        if executable == "git":
            arguments, message_cwd = git_commit(words, cwd)
            inline_long, inline_short = {"--message"}, {"-m"}
            file_long, file_short = {"--file", "--template"}, {"-F", "-t"}
        elif executable == "gh":
            arguments = gh_write(words)
            inline_long, inline_short = {"--title", "--body"}, {"-t", "-b"}
            file_long, file_short = {"--body-file"}, {"-F"}
        else:
            continue
        if arguments is None:
            continue
        messages = list(option_values(arguments, inline_long, inline_short))
        for filename in option_values(arguments, file_long, file_short):
            if filename == "-":
                raise ValueError("cannot inspect a message read from stdin; use a message file")
            try:
                messages.append((message_cwd / filename).read_text(encoding="utf-8"))
            except (OSError, UnicodeError):
                raise ValueError("cannot read the message file; use a readable UTF-8 file") from None
        if any(ATTRIBUTION.search(message) for message in messages):
            raise ValueError(
                "remove the Claude Co-Authored-By trailer / 'Generated with Claude Code' footer. "
                "Global rule: no agent attribution in commits or PR bodies."
            )


def main():
    event = json.load(sys.stdin)
    try:
        inspect(event.get("tool_input", {}).get("command", ""),
                Path(event.get("cwd") or Path.cwd()))
    except ValueError as error:
        print(f"Blocked: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
