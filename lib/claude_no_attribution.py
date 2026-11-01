"""Inspect literal shell arguments without evaluating shell code or expansions.

This is a guard for ordinary Git/gh invocations, not a shell interpreter. Dynamic
messages (command substitutions, stdin, etc.) cannot be fully inspected here.
"""

import json
import os
from pathlib import Path
import re
import shlex
import sys


ATTRIBUTION = re.compile(
    r"co-authored-by\s*[:=].*(?:claude|anthropic)|generated with.*claude code|"
    r"claude\.com/claude-code",
    re.IGNORECASE,
)
HEREDOC = re.compile(r"<<(?!<)(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
STDIN_PATHS = {"-", "/dev/stdin", "/dev/fd/0", "/proc/self/fd/0", "/proc/self/fd/0/"}


def strip_heredocs(command):
    """Return (command without heredoc bodies, bodies).

    Bodies are free text, not shell, so they must not reach the tokenizer
    (unmatched quotes in them are valid). They are returned so they can still be
    scanned when the command also writes a commit or PR message.
    """
    kept, bodies, queue, active = [], [], [], None
    for line in command.split("\n"):
        if active is not None:
            dash, delimiter = active
            if (line.lstrip("\t") if dash else line) == delimiter:
                active = queue.pop(0) if queue else None
            else:
                bodies.append(line)
            continue
        kept.append(line)
        queue = [(dash == "-", delimiter) for dash, _, delimiter in HEREDOC.findall(line)]
        active = queue.pop(0) if queue else None
    return "\n".join(kept), bodies


ATTRIBUTION_MESSAGE = (
    "remove the Claude Co-Authored-By trailer / 'Generated with Claude Code' footer. "
    "Global rule: no agent attribution in commits or PR bodies."
)


def commands(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    # Shlex would swallow the newline that ends a comment, merging the next
    # command into this one; handle comments here so command boundaries survive.
    lexer.commenters = ""
    words = []
    in_comment = False
    for word in lexer:
        if word and all(character in ";&|()\n" for character in word):
            if in_comment and "\n" not in word:
                continue
            in_comment = False
            if words:
                yield words
            words = []
        elif in_comment:
            continue
        elif not words and word.startswith("#"):
            in_comment = True
        else:
            words.append(word)
    if words:
        yield words


def option_values(arguments, long_names, short_names, valued_short=frozenset()):
    """Yield literal values of message options, including attached and bundled forms.

    `valued_short` lists other short flags that take a value, so that in
    `-Fmessage.txt` the `m` is not mistaken for the message option.
    """
    index = 0
    while index < len(arguments):
        word = arguments[index]
        if word == "--":
            return
        if word.startswith("--"):
            if word in long_names:
                index += 1
                if index < len(arguments):
                    yield arguments[index]
            elif any(word.startswith(name + "=") for name in long_names):
                yield word.split("=", 1)[1]
        elif word.startswith("-") and len(word) > 1:
            for position, flag in enumerate(word[1:], 1):
                if flag in short_names:
                    rest = word[position + 1 :]
                    if rest:
                        yield rest
                    else:
                        index += 1
                        if index < len(arguments):
                            yield arguments[index]
                    break
                if flag in valued_short:
                    break
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


GH_ACTIONS = {
    "pr": {"create", "edit", "comment", "review", "merge", "close"},
    "issue": {"create", "edit", "comment", "close"},
}


def gh_write(words):
    index = 1
    while index < len(words) and words[index].startswith("-"):
        if words[index] in {"-R", "--repo", "--hostname"}:
            index += 1
        index += 1
    if index + 1 >= len(words):
        return None
    resource, action = words[index : index + 2]
    if action in GH_ACTIONS.get(resource, ()):
        return words[index + 2 :]
    return None


def stdin_backed(filename):
    return os.path.normpath(filename) in STDIN_PATHS or filename in STDIN_PATHS


def inspect(command, cwd):
    command, bodies = strip_heredocs(command)
    writes = False
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
            inline_long, inline_short = {"--message", "--trailer"}, {"m"}
            file_long, file_short = {"--file", "--template"}, {"F", "t"}
            other_short = {"C", "c", "u", "S"}
        elif executable == "gh":
            arguments = gh_write(words)
            inline_long = {"--title", "--body", "--subject", "--comment"}
            inline_short = {"t", "b", "c"}
            file_long, file_short = {"--body-file"}, {"F"}
            other_short = {"R", "a", "l", "m", "p", "r", "B", "H", "T"}
        else:
            continue
        if arguments is None:
            continue
        writes = True
        valued = inline_short | file_short | other_short
        messages = list(option_values(arguments, inline_long, inline_short, valued - inline_short))
        for filename in option_values(arguments, file_long, file_short, valued - file_short):
            if stdin_backed(filename):
                raise ValueError("cannot inspect a message read from stdin; use a message file")
            try:
                messages.append((message_cwd / filename).read_text(encoding="utf-8"))
            except (OSError, UnicodeError):
                raise ValueError("cannot read the message file; use a readable UTF-8 file") from None
        if any(ATTRIBUTION.search(message) for message in messages):
            raise ValueError(ATTRIBUTION_MESSAGE)
    if writes and ATTRIBUTION.search("\n".join(bodies)):
        raise ValueError(ATTRIBUTION_MESSAGE)


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
