#!/usr/bin/env python3
"""Materialise every unique SSH key in 1Password as a file in ~/.ssh.

1Password remains the source of truth. The script reads every SSH Key item
from every configured account, collapses items that hold the same key (they
are identified by fingerprint, not title), and writes one private key and one
.pub file per unique key.

Files are only written when their content differs. A manifest records what
this script created, so a key deleted in 1Password can be removed from disk
without ever deleting a file the script did not write.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass, field
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata

MANIFEST_NAME = ".1password-ssh-keys.json"
MANIFEST_VERSION = 1
MAX_NAME_LENGTH = 64
PRIVATE_MODE = 0o600
PUBLIC_MODE = 0o644
SSH_DIR_MODE = 0o700


class SyncError(Exception):
    """A failure that must stop the run before any files are changed."""


@dataclass(frozen=True)
class Account:
    url: str
    email: str = ""


@dataclass(frozen=True)
class Source:
    account: str
    vault: str
    item_id: str
    title: str


@dataclass
class Key:
    fingerprint: str
    key_type: str
    private_key: str
    public_key: str
    sources: list[Source] = field(default_factory=list)

    @property
    def primary(self) -> Source:
        return sorted(self.sources, key=source_rank)[0]


@dataclass
class Result:
    created: list[tuple[str, Key]] = field(default_factory=list)
    updated: list[tuple[str, Key]] = field(default_factory=list)
    unchanged: list[tuple[str, Key]] = field(default_factory=list)
    adopted: list[tuple[str, Key]] = field(default_factory=list)
    renamed: list[tuple[str, Key]] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    accounts: list[str] = field(default_factory=list)
    item_count: int = 0
    key_count: int = 0
    ssh_dir: str = ""
    dry_run: bool = False


def run_op(arguments: list[str]) -> str:
    """Run the 1Password CLI and return stdout, raising SyncError on failure."""
    try:
        completed = subprocess.run(
            ["op", *arguments],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise SyncError("the 1Password CLI (op) is not installed") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        message = detail[-1] if detail else f"op exited {completed.returncode}"
        raise SyncError(f"op {' '.join(arguments)}: {message}")
    return completed.stdout


def slugify(value: str) -> str:
    """Turn a title into a safe, portable filename stem."""
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:MAX_NAME_LENGTH].rstrip("-")


def short_fingerprint(fingerprint: str) -> str:
    digest = fingerprint.split(":", 1)[-1]
    compact = re.sub(r"[^A-Za-z0-9]", "", digest)
    return (compact or hashlib.sha256(fingerprint.encode("utf-8")).hexdigest())[:8]


def title_rank(title: str) -> int:
    """Rank generic titles after descriptive ones when picking a filename."""
    return 1 if re.match(r"^(ssh|key|id)([-_ ]|$)", title.strip(), re.IGNORECASE) else 0


def source_rank(source: Source) -> tuple:
    return (
        title_rank(source.title),
        len(source.title),
        source.title.casefold(),
        source.account,
        source.vault,
        source.item_id,
    )


def fingerprint_of(public_key: str) -> str:
    """Compute an OpenSSH SHA256 fingerprint from a public key line."""
    parts = public_key.split()
    if len(parts) >= 2:
        try:
            blob = base64.b64decode(parts[1], validate=True)
        except (ValueError, TypeError):
            blob = b""
        if blob:
            digest = hashlib.sha256(blob).digest()
            return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")
    return "SHA256:" + hashlib.sha256(public_key.encode("utf-8")).hexdigest()


def as_openssh(private_key: str) -> str | None:
    """Return an OpenSSH-format private key, converting it if needed."""
    private_key = private_key.strip()
    if not private_key:
        return None
    if private_key.startswith("-----BEGIN OPENSSH PRIVATE KEY-----"):
        return private_key
    keygen = shutil.which("ssh-keygen")
    if not keygen:
        return None
    with tempfile.TemporaryDirectory(prefix="ssh-keys-sync-") as directory:
        path = Path(directory) / "key"
        path.write_text(private_key + "\n", encoding="utf-8")
        path.chmod(PRIVATE_MODE)
        completed = subprocess.run(
            [keygen, "-p", "-P", "", "-N", "", "-m", "OPENSSH", "-f", str(path)],
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            return None
        converted = path.read_text(encoding="utf-8").strip()
    return converted or None


def field_value(item: dict, field_id: str) -> str:
    for entry in item.get("fields") or []:
        if entry.get("id") == field_id:
            return str(entry.get("value") or "").strip()
    return ""


def openssh_private_key(item: dict) -> str | None:
    private_field = next(
        (entry for entry in item.get("fields") or [] if entry.get("id") == "private_key"),
        None,
    )
    if not private_field:
        return None
    formats = private_field.get("ssh_formats") or {}
    openssh = (formats.get("openssh") or {}).get("value")
    raw = openssh or private_field.get("value") or ""
    return as_openssh(str(raw))


def list_accounts(op=run_op) -> list[Account]:
    entries = json.loads(op(["account", "list", "--format", "json"]) or "[]")
    accounts = []
    for entry in entries:
        url = str(entry.get("url") or "").strip()
        if url:
            accounts.append(Account(url=url, email=str(entry.get("email") or "").strip()))
    return accounts


def select_accounts(accounts: list[Account], requested: list[str]) -> list[Account]:
    if not requested:
        return accounts
    selected: list[Account] = []
    known = ", ".join(account.url for account in accounts) or "none"
    for value in requested:
        needle = value.strip().lower()
        matches = [
            account
            for account in accounts
            if needle in (account.url.lower(), account.email.lower())
        ]
        if not matches:
            raise SyncError(f"unknown account {value!r}; configured accounts: {known}")
        for match in matches:
            if match not in selected:
                selected.append(match)
    return selected


def list_ssh_items(op, account: Account) -> list[dict]:
    return json.loads(
        op(
            [
                "item",
                "list",
                "--account",
                account.url,
                "--categories",
                "SSH Key",
                "--format",
                "json",
            ]
        )
        or "[]"
    )


def fetch_item(op, account: Account, item_id: str) -> dict:
    return json.loads(
        op(
            [
                "item",
                "get",
                item_id,
                "--account",
                account.url,
                "--format",
                "json",
                "--reveal",
            ]
        )
        or "{}"
    )


def extract_key(account: Account, item: dict) -> Key | None:
    public_key = field_value(item, "public_key")
    private_key = openssh_private_key(item)
    if not public_key or not private_key:
        return None
    fingerprint = field_value(item, "fingerprint") or fingerprint_of(public_key)
    vault = str((item.get("vault") or {}).get("name") or "").strip()
    source = Source(
        account=account.url,
        vault=vault,
        item_id=str(item.get("id") or ""),
        title=str(item.get("title") or "").strip() or "SSH key",
    )
    return Key(
        fingerprint=fingerprint,
        key_type=field_value(item, "key_type") or "unknown",
        private_key=private_key,
        public_key=public_key,
        sources=[source],
    )


def collect_keys(
    op, accounts: list[Account], warnings: list[str]
) -> tuple[dict[str, Key], int]:
    """Read every SSH Key item, returning unique keys and the item count."""
    keys: dict[str, Key] = {}
    item_count = 0
    for account in accounts:
        for item in list_ssh_items(op, account):
            item_count += 1
            full_item = fetch_item(op, account, str(item.get("id") or ""))
            key = extract_key(account, full_item)
            if key is None:
                title = item.get("title") or full_item.get("title") or "untitled"
                vault = (item.get("vault") or {}).get("name") or "unknown vault"
                warnings.append(
                    f"skipped {title!r} in {vault} ({account.url}): no private key "
                    "that can be exported in OpenSSH format"
                )
                continue
            existing = keys.get(key.fingerprint)
            if existing is None:
                keys[key.fingerprint] = key
            else:
                existing.sources.extend(key.sources)
    return keys, item_count


def plan_names(
    keys: dict[str, Key], known_names: dict[str, str], reserved: set[str]
) -> dict[str, str]:
    """Give every unique key a filename stem.

    A name this script already used for a fingerprint is kept, so renaming an
    item in 1Password does not churn files on disk. Different keys that would
    share a name are separated by their vault, then by fingerprint.
    """
    used = set(reserved)
    names: dict[str, str] = {}

    # Remembered names come first, so an edited title cannot steal one.
    for fingerprint, _key in keys.items():
        remembered = known_names.get(fingerprint)
        if remembered and remembered not in used:
            names[fingerprint] = remembered
            used.add(remembered)

    grouped: dict[str, list[str]] = {}
    for fingerprint, key in keys.items():
        if fingerprint in names:
            continue
        base = slugify(key.primary.title) or f"ssh-key-{short_fingerprint(fingerprint)}"
        if title_rank(key.primary.title):
            # "SSH Key" alone says nothing; say which vault it came from.
            vault = slugify(key.primary.vault)
            if vault:
                base = f"{vault}-{base}"
        grouped.setdefault(base, []).append(fingerprint)

    for base in sorted(grouped):
        fingerprints = grouped[base]
        if len(fingerprints) == 1:
            fingerprint = fingerprints[0]
            names[fingerprint] = make_unique(base, fingerprint, used)
            continue
        for fingerprint in sorted(fingerprints):
            vault = slugify(keys[fingerprint].primary.vault)
            candidate = f"{base}-{vault}" if vault else base
            names[fingerprint] = make_unique(candidate, fingerprint, used)
    return names


def make_unique(candidate: str, fingerprint: str, used: set[str]) -> str:
    name = candidate
    if name in used:
        name = f"{candidate}-{short_fingerprint(fingerprint)}"
    suffix = 2
    while name in used:
        name = f"{candidate}-{short_fingerprint(fingerprint)}-{suffix}"
        suffix += 1
    used.add(name)
    return name


def private_key_content(key: Key) -> str:
    return key.private_key.strip() + "\n"


def public_key_content(key: Key) -> str:
    return key.public_key.strip() + "\n"


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def files_match(path: Path, content: str) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    current = read_text(path)
    return current is not None and current == content


def write_file(path: Path, content: str, mode: int, dry_run: bool) -> bool:
    """Write content atomically, returning True when the file changed."""
    if files_match(path, content):
        if not dry_run:
            os.chmod(path, mode)
        return False
    if dry_run:
        return True
    descriptor, temporary = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def choose_name(
    ssh_dir: Path,
    name: str,
    key: Key,
    owned: bool,
) -> tuple[str, str | None]:
    """Resolve collisions with files this script did not create.

    Returns the chosen stem and a status ("adopted" or "renamed"), or
    (name, None) when the target is free or already owned by the manifest.
    """
    private_path = ssh_dir / name
    public_path = ssh_dir / f"{name}.pub"
    if owned:
        if private_path.is_symlink() or public_path.is_symlink():
            raise SyncError(
                f"{private_path} is recorded in the manifest but is now a symlink; "
                "refusing to write through it"
            )
        return name, None

    private_content = private_key_content(key)
    public_content = public_key_content(key)
    if not private_path.exists() and not private_path.is_symlink():
        if not public_path.exists() and not public_path.is_symlink():
            return name, None
    if files_match(private_path, private_content) and files_match(public_path, public_content):
        return name, "adopted"

    candidate = f"{name}-{short_fingerprint(key.fingerprint)}"
    suffix = 2
    while True:
        candidate_private = ssh_dir / candidate
        candidate_public = ssh_dir / f"{candidate}.pub"
        if not candidate_private.exists() and not candidate_private.is_symlink():
            if not candidate_public.exists() and not candidate_public.is_symlink():
                return candidate, "renamed"
        if files_match(candidate_private, private_content) and files_match(
            candidate_public, public_content
        ):
            return candidate, "adopted"
        candidate = f"{name}-{short_fingerprint(key.fingerprint)}-{suffix}"
        suffix += 1


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {"version": MANIFEST_VERSION, "keys": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SyncError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("keys"), dict):
        raise SyncError(f"manifest {path} is not in the expected format")
    return data


def manifest_entry(key: Key) -> dict:
    private_content = private_key_content(key)
    return {
        "fingerprint": key.fingerprint,
        "key_type": key.key_type,
        "public_key": key.public_key.strip(),
        "private_key_sha256": hashlib.sha256(private_content.encode("utf-8")).hexdigest(),
        "account": key.primary.account,
        "accounts": sorted({source.account for source in key.sources}),
        "vault": key.primary.vault,
        "title": key.primary.title,
        "item_id": key.primary.item_id,
        "sources": [
            {
                "account": source.account,
                "vault": source.vault,
                "item_id": source.item_id,
                "title": source.title,
            }
            for source in sorted(key.sources, key=source_rank)
        ],
    }


def prune(
    ssh_dir: Path,
    name: str,
    entry: dict,
    result: Result,
    dry_run: bool,
) -> bool:
    """Remove a file this script wrote, returning True if it is gone."""
    private_path = ssh_dir / name
    public_path = ssh_dir / f"{name}.pub"
    if private_path.is_symlink():
        result.warnings.append(f"left {private_path} alone: it is a symlink, not a file we wrote")
        return False
    if not private_path.exists():
        return True
    current = read_text(private_path)
    expected = entry.get("private_key_sha256")
    if current is None or hashlib.sha256(current.encode("utf-8")).hexdigest() != expected:
        result.warnings.append(
            f"left {private_path} alone: it was modified after the last sync"
        )
        return False
    if not dry_run:
        private_path.unlink()
        if public_path.is_file() and not public_path.is_symlink():
            public_path.unlink()
    result.removed.append(name)
    return True


def sync(args: argparse.Namespace, op=run_op) -> Result:
    ssh_dir = Path(args.ssh_dir).expanduser()
    manifest_path = ssh_dir / MANIFEST_NAME

    accounts = select_accounts(list_accounts(op), args.accounts)
    if not accounts:
        raise SyncError("no 1Password accounts are configured; run 'op account add' first")

    old_manifest = load_manifest(manifest_path)
    old_entries: dict[str, dict] = old_manifest["keys"]

    result = Result()
    keys, item_count = collect_keys(op, accounts, result.warnings)

    known_names = {
        entry.get("fingerprint"): name
        for name, entry in old_entries.items()
        if entry.get("fingerprint")
    }
    synced_accounts = {account.url for account in accounts}
    removable = {
        name
        for name, entry in old_entries.items()
        if set(entry.get("accounts") or [entry.get("account")]) <= synced_accounts
    }
    reserved = set(old_entries) - removable - set(known_names.values())
    names = plan_names(keys, known_names, reserved)

    if not args.dry_run:
        ssh_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(ssh_dir, SSH_DIR_MODE)

    new_entries: dict[str, dict] = {}
    planned: list[tuple[str, Key, str | None]] = []
    for fingerprint, key in sorted(keys.items(), key=lambda pair: names[pair[0]]):
        name = names[fingerprint]
        owned = name in old_entries and old_entries[name].get("fingerprint") == fingerprint
        name, status = choose_name(ssh_dir, name, key, owned)
        planned.append((name, key, status))

    for name, key, status in planned:
        private_path = ssh_dir / name
        public_path = ssh_dir / f"{name}.pub"
        existed = private_path.exists() or private_path.is_symlink()

        changed = write_file(
            private_path, private_key_content(key), PRIVATE_MODE, args.dry_run
        )
        changed = (
            write_file(public_path, public_key_content(key), PUBLIC_MODE, args.dry_run)
            or changed
        )

        labelled = (name, key)
        if status == "adopted":
            result.adopted.append(labelled)
        elif status == "renamed":
            result.renamed.append(labelled)
        elif not existed:
            result.created.append(labelled)
        elif changed:
            result.updated.append(labelled)
        else:
            result.unchanged.append(labelled)

        new_entries[name] = manifest_entry(key)

    kept_entries: dict[str, dict] = {}
    if args.dry_run:
        kept_entries = {
            name: entry for name, entry in old_entries.items() if name not in new_entries
        }
        if not args.no_prune:
            for name, entry in sorted(old_entries.items()):
                if name in new_entries or name not in removable:
                    continue
                prune(ssh_dir, name, entry, result, dry_run=True)
    else:
        for name, entry in sorted(old_entries.items()):
            if name in new_entries:
                continue
            if name in removable and not args.no_prune:
                if prune(ssh_dir, name, entry, result, dry_run=False):
                    continue
            kept_entries[name] = entry

    manifest_keys = dict(sorted({**kept_entries, **new_entries}.items()))
    manifest = {
        "version": MANIFEST_VERSION,
        "synced_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "keys": manifest_keys,
    }
    if not args.dry_run and (
        old_manifest.get("keys") != manifest_keys
        or old_manifest.get("version") != MANIFEST_VERSION
    ):
        write_file(
            manifest_path,
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            PRIVATE_MODE,
            dry_run=False,
        )

    result.accounts = [account.url for account in accounts]
    result.item_count = item_count
    result.key_count = len(keys)
    result.ssh_dir = str(ssh_dir)
    result.dry_run = bool(args.dry_run)
    return result


def describe(pair: tuple[str, Key]) -> str:
    name, key = pair
    source = key.primary
    vault = source.vault or "unknown vault"
    line = f"  {name:<32} {key.fingerprint:<52} {source.title} [{vault}] ({source.account})"
    return line.rstrip()


def report(result: Result, verbose: bool, out=sys.stdout, err=sys.stderr) -> None:
    prefix = "Would " if result.dry_run else ""
    groups = [
        (f"{prefix}create", result.created),
        (f"{prefix}update", result.updated),
        (f"{prefix}adopt", result.adopted),
        (f"{prefix}rename", result.renamed),
        (f"{prefix}remove", [(name, None) for name in result.removed]),
    ]
    for label, pairs in groups:
        if not pairs:
            continue
        print(f"{label}:", file=out)
        for pair in pairs:
            if pair[1] is None:
                print(f"  {pair[0]}", file=out)
            else:
                print(describe(pair), file=out)
    if verbose:
        if result.unchanged:
            print("unchanged:", file=out)
            for pair in result.unchanged:
                print(describe(pair), file=out)

    for warning in result.warnings:
        print(f"warning: {warning}", file=err)

    counts = [
        f"{len(result.created)} created",
        f"{len(result.updated)} updated",
        f"{len(result.unchanged)} unchanged",
    ]
    if result.adopted:
        counts.append(f"{len(result.adopted)} adopted")
    if result.renamed:
        counts.append(f"{len(result.renamed)} renamed")
    if result.removed:
        counts.append(f"{len(result.removed)} removed")
    accounts = ", ".join(sorted(result.accounts))
    print(
        f"{result.key_count} unique keys from {result.item_count} items "
        f"across {len(result.accounts)} account(s) ({accounts}); "
        + ", ".join(counts)
        + f"; target {result.ssh_dir}",
        file=out,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ssh-keys-sync",
        description=(
            "Write every unique SSH key in 1Password to ~/.ssh. 1Password stays "
            "the source of truth; this exists for tools that need a key file."
        ),
    )
    parser.add_argument(
        "--ssh-dir",
        default="~/.ssh",
        help="directory to write keys into (default: ~/.ssh)",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="show what would change without writing anything",
    )
    parser.add_argument(
        "--no-prune",
        action="store_true",
        help="keep files whose keys have gone from 1Password",
    )
    parser.add_argument(
        "--account",
        action="append",
        default=[],
        dest="accounts",
        metavar="URL",
        help="only sync this account (repeatable; URL or email)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="also list keys that were already up to date",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = sync(args)
    except SyncError as exc:
        print(f"ssh-keys-sync: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ssh-keys-sync: interrupted", file=sys.stderr)
        return 130
    report(result, args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
