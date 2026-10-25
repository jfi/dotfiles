"""Behavioural tests for ssh-keys-sync; no 1Password account needed."""

import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "ssh_keys_sync", Path(__file__).resolve().parents[1] / "lib" / "ssh_keys_sync.py"
)
sync = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sync
SPEC.loader.exec_module(sync)

ACCOUNTS = [
    {"url": "my.1password.eu", "email": "james@example.com"},
    {"url": "neurobetter.1password.com", "email": "james@neurobetter.org"},
]

PRIVATE_KEY = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW\n"
    "-----END OPENSSH PRIVATE KEY-----"
)


def public_key(fingerprint):
    blob = fingerprint.encode("utf-8")
    return "ssh-ed25519 " + base64.b64encode(blob).decode("ascii") + " user@example"


def item(
    item_id,
    title,
    fingerprint,
    vault="Alder CRM",
    account="my.1password.eu",
    private_key=PRIVATE_KEY,
    openssh=None,
):
    private_field = {"id": "private_key", "type": "SSHKEY", "value": private_key}
    if openssh is not None:
        private_field["ssh_formats"] = {"openssh": {"value": openssh}}
    return {
        "id": item_id,
        "title": title,
        "vault": {"id": f"{vault}-id", "name": vault},
        "category": "SSH_KEY",
        "fields": [
            {"id": "public_key", "value": public_key(fingerprint)},
            {"id": "fingerprint", "value": fingerprint},
            {"id": "key_type", "value": "ed25519"},
            private_field,
        ],
        "_account": account,
    }


class FakeOp:
    """Stands in for the 1Password CLI, keyed by account and item id."""

    def __init__(self, accounts, items, fail_on_get=False):
        self.accounts = accounts
        self.items = {entry["id"]: entry for entry in items}
        self.fail_on_get = fail_on_get

    def __call__(self, arguments):
        if arguments == ["account", "list", "--format", "json"]:
            return json.dumps(self.accounts)
        if arguments[:2] == ["item", "list"]:
            account = arguments[arguments.index("--account") + 1]
            listed = [
                {"id": entry["id"], "title": entry["title"], "vault": entry["vault"]}
                for entry in self.items.values()
                if entry["_account"] == account
            ]
            return json.dumps(listed)
        if arguments[:2] == ["item", "get"]:
            if self.fail_on_get:
                raise sync.SyncError("authorization timeout")
            return json.dumps(self.items[arguments[2]])
        raise AssertionError(f"unexpected op invocation: {arguments}")


def namespace(ssh_dir, **overrides):
    values = {
        "ssh_dir": str(ssh_dir),
        "dry_run": False,
        "no_prune": False,
        "accounts": [],
        "verbose": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def key(fingerprint, title, vault="Alder CRM", account="my.1password.eu", item_id=None):
    return sync.Key(
        fingerprint=fingerprint,
        key_type="ed25519",
        private_key=PRIVATE_KEY,
        public_key=public_key(fingerprint),
        sources=[
            sync.Source(
                account=account,
                vault=vault,
                item_id=item_id or fingerprint,
                title=title,
            )
        ],
    )


def manifest_of(ssh_dir):
    return json.loads((Path(ssh_dir) / sync.MANIFEST_NAME).read_text(encoding="utf-8"))


class SlugifyTests(unittest.TestCase):
    def test_makes_a_safe_portable_stem(self):
        self.assertEqual(sync.slugify("AlderCRM Infra"), "aldercrm-infra")
        self.assertEqual(sync.slugify("  Café  Key!! "), "cafe-key")
        self.assertEqual(sync.slugify("Engineering: Production"), "engineering-production")

    def test_empty_and_punctuation_only(self):
        self.assertEqual(sync.slugify("---"), "")
        self.assertEqual(sync.slugify(""), "")


class FingerprintTests(unittest.TestCase):
    def test_computes_openssh_sha256_from_the_public_key(self):
        blob = b"fake-key-blob"
        line = "ssh-ed25519 " + base64.b64encode(blob).decode("ascii") + " user@test"
        digest = hashlib.sha256(blob).digest()
        expected = "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")
        self.assertEqual(sync.fingerprint_of(line), expected)


class PlanNameTests(unittest.TestCase):
    def test_duplicate_titles_are_separated_by_vault(self):
        keys = {
            "SHA256:aaa": key("SHA256:aaa", "deploy", "Engineering: Staging"),
            "SHA256:bbb": key("SHA256:bbb", "deploy", "Engineering: Production"),
        }
        names = sync.plan_names(keys, {}, set())
        self.assertEqual(
            sorted(names.values()),
            ["deploy-engineering-production", "deploy-engineering-staging"],
        )

    def test_generic_title_is_prefixed_with_its_vault(self):
        names = sync.plan_names({"SHA256:aaa": key("SHA256:aaa", "SSH Key", "Otaina")}, {}, set())
        self.assertEqual(names["SHA256:aaa"], "otaina-ssh-key")

    def test_remembers_the_name_already_used_for_a_fingerprint(self):
        names = sync.plan_names(
            {"SHA256:aaa": key("SHA256:aaa", "A New Title")}, {"SHA256:aaa": "old-name"}, set()
        )
        self.assertEqual(names["SHA256:aaa"], "old-name")

    def test_never_reuses_a_reserved_name(self):
        names = sync.plan_names(
            {"SHA256:aaa": key("SHA256:aaa", "pumbaa")}, {}, {"pumbaa"}
        )
        self.assertNotEqual(names["SHA256:aaa"], "pumbaa")


class SyncTests(unittest.TestCase):
    def test_writes_one_private_and_one_public_file(self):
        with tempfile.TemporaryDirectory() as directory:
            ssh_dir = Path(directory)
            op = FakeOp(ACCOUNTS, [item("i1", "AlderCRM Infra", "SHA256:aaa")])
            result = sync.sync(namespace(ssh_dir), op=op)

            private = ssh_dir / "aldercrm-infra"
            public = ssh_dir / "aldercrm-infra.pub"
            self.assertEqual(private.read_text(), PRIVATE_KEY + "\n")
            self.assertEqual(public.read_text(), public_key("SHA256:aaa") + "\n")
            self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(public.stat().st_mode), 0o644)
            self.assertEqual(len(result.created), 1)
            self.assertEqual(result.item_count, 1)
            self.assertEqual(result.key_count, 1)

    def test_manifest_is_private_and_records_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            ssh_dir = Path(directory)
            op = FakeOp(ACCOUNTS, [item("i1", "AlderCRM Infra", "SHA256:aaa")])
            sync.sync(namespace(ssh_dir), op=op)

            path = ssh_dir / sync.MANIFEST_NAME
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            entry = manifest_of(ssh_dir)["keys"]["aldercrm-infra"]
            self.assertEqual(entry["fingerprint"], "SHA256:aaa")
            self.assertEqual(entry["item_id"], "i1")
            self.assertEqual(entry["accounts"], ["my.1password.eu"])
            self.assertEqual(entry["sources"][0]["vault"], "Alder CRM")
            self.assertNotIn("private_key", entry)
            self.assertEqual(
                entry["private_key_sha256"],
                hashlib.sha256((PRIVATE_KEY + "\n").encode()).hexdigest(),
            )

    def test_items_holding_the_same_key_become_one_file(self):
        with tempfile.TemporaryDirectory() as directory:
            ssh_dir = Path(directory)
            op = FakeOp(
                ACCOUNTS,
                [
                    item("i1", "SSH Key", "SHA256:same", vault="Otaina"),
                    item("i2", "SSH Key (ED25519)", "SHA256:same", vault="Personal"),
                    item(
                        "i3",
                        "SSH Key (ED25519)",
                        "SHA256:same",
                        vault="Employee",
                        account="neurobetter.1password.com",
                    ),
                ],
            )
            result = sync.sync(namespace(ssh_dir), op=op)

            self.assertEqual(result.key_count, 1)
            self.assertEqual(result.item_count, 3)
            self.assertEqual(len(result.created), 1)
            self.assertEqual(
                sorted(path.name for path in ssh_dir.iterdir()),
                [sync.MANIFEST_NAME, "otaina-ssh-key", "otaina-ssh-key.pub"],
            )
            entry = manifest_of(ssh_dir)["keys"]["otaina-ssh-key"]
            self.assertEqual(len(entry["sources"]), 3)
            self.assertEqual(
                sorted(entry["accounts"]), ["my.1password.eu", "neurobetter.1password.com"]
            )

    def test_the_openssh_export_is_written_not_the_raw_field(self):
        with tempfile.TemporaryDirectory() as directory:
            ssh_dir = Path(directory)
            openssh = "-----BEGIN OPENSSH PRIVATE KEY-----\nconverted\n-----END OPENSSH PRIVATE KEY-----"
            op = FakeOp(
                ACCOUNTS,
                [
                    item(
                        "i1",
                        "AlderCRM Infra",
                        "SHA256:aaa",
                        private_key="-----BEGIN PRIVATE KEY-----\npkcs8\n-----END PRIVATE KEY-----",
                        openssh=openssh,
                    )
                ],
            )
            sync.sync(namespace(ssh_dir), op=op)
            self.assertEqual((ssh_dir / "aldercrm-infra").read_text(), openssh + "\n")

    def test_second_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            ssh_dir = Path(directory)
            op = FakeOp(ACCOUNTS, [item("i1", "AlderCRM Infra", "SHA256:aaa")])
            sync.sync(namespace(ssh_dir), op=op)
            before = (ssh_dir / "aldercrm-infra").stat().st_mtime_ns
            after_manifest = (ssh_dir / sync.MANIFEST_NAME).stat().st_mtime_ns

            result = sync.sync(namespace(ssh_dir), op=op)

            self.assertEqual(result.created, [])
            self.assertEqual(result.updated, [])
            self.assertEqual(len(result.unchanged), 1)
            self.assertEqual((ssh_dir / "aldercrm-infra").stat().st_mtime_ns, before)
            self.assertEqual(
                (ssh_dir / sync.MANIFEST_NAME).stat().st_mtime_ns, after_manifest
            )

    def test_never_overwrites_a_file_it_did_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            ssh_dir = Path(directory)
            existing = ssh_dir / "pumbaa"
            existing.write_text("someone else's key\n", encoding="utf-8")
            op = FakeOp(ACCOUNTS, [item("i1", "pumbaa", "SHA256:abcdef123456")])

            result = sync.sync(namespace(ssh_dir), op=op)

            self.assertEqual(existing.read_text(), "someone else's key\n")
            alternative = ssh_dir / "pumbaa-abcdef12"
            self.assertTrue(alternative.exists())
            self.assertEqual(len(result.renamed), 1)

    def test_adopts_an_identical_file_it_did_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            ssh_dir = Path(directory)
            (ssh_dir / "pumbaa").write_text(PRIVATE_KEY + "\n", encoding="utf-8")
            (ssh_dir / "pumbaa.pub").write_text(
                public_key("SHA256:aaa") + "\n", encoding="utf-8"
            )
            op = FakeOp(ACCOUNTS, [item("i1", "pumbaa", "SHA256:aaa")])

            result = sync.sync(namespace(ssh_dir), op=op)

            self.assertEqual(len(result.adopted), 1)
            self.assertIn("pumbaa", manifest_of(ssh_dir)["keys"])

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            ssh_dir = Path(directory) / "missing"
            op = FakeOp(ACCOUNTS, [item("i1", "AlderCRM Infra", "SHA256:aaa")])

            result = sync.sync(namespace(ssh_dir, dry_run=True), op=op)

            self.assertFalse(ssh_dir.exists())
            self.assertEqual(len(result.created), 1)

    def test_removes_a_key_that_has_gone_from_1password(self):
        with tempfile.TemporaryDirectory() as directory:
            ssh_dir = Path(directory)
            sync.sync(
                namespace(ssh_dir),
                op=FakeOp(ACCOUNTS, [item("i1", "pumbaa", "SHA256:aaa")]),
            )
            result = sync.sync(namespace(ssh_dir), op=FakeOp(ACCOUNTS, []))

            self.assertEqual(result.removed, ["pumbaa"])
            self.assertFalse((ssh_dir / "pumbaa").exists())
            self.assertFalse((ssh_dir / "pumbaa.pub").exists())
            self.assertEqual(manifest_of(ssh_dir)["keys"], {})

    def test_keeps_a_file_modified_after_the_last_sync(self):
        with tempfile.TemporaryDirectory() as directory:
            ssh_dir = Path(directory)
            sync.sync(
                namespace(ssh_dir),
                op=FakeOp(ACCOUNTS, [item("i1", "pumbaa", "SHA256:aaa")]),
            )
            (ssh_dir / "pumbaa").write_text("edited by hand\n", encoding="utf-8")

            result = sync.sync(namespace(ssh_dir), op=FakeOp(ACCOUNTS, []))

            self.assertEqual(result.removed, [])
            self.assertEqual((ssh_dir / "pumbaa").read_text(), "edited by hand\n")
            self.assertTrue(any("modified" in warning for warning in result.warnings))
            self.assertIn("pumbaa", manifest_of(ssh_dir)["keys"])

    def test_no_prune_keeps_files_and_manifest_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            ssh_dir = Path(directory)
            sync.sync(
                namespace(ssh_dir),
                op=FakeOp(ACCOUNTS, [item("i1", "pumbaa", "SHA256:aaa")]),
            )
            result = sync.sync(
                namespace(ssh_dir, no_prune=True), op=FakeOp(ACCOUNTS, [])
            )

            self.assertEqual(result.removed, [])
            self.assertTrue((ssh_dir / "pumbaa").exists())
            self.assertIn("pumbaa", manifest_of(ssh_dir)["keys"])

    def test_account_filter_only_touches_that_account(self):
        with tempfile.TemporaryDirectory() as directory:
            ssh_dir = Path(directory)
            items = [
                item("i1", "pumbaa", "SHA256:aaa"),
                item(
                    "i2",
                    "neurobetter SSH Key",
                    "SHA256:bbb",
                    vault="Employee",
                    account="neurobetter.1password.com",
                ),
            ]
            sync.sync(namespace(ssh_dir), op=FakeOp(ACCOUNTS, items))
            (ssh_dir / "pumbaa.pub").unlink()
            (ssh_dir / "pumbaa").unlink()

            result = sync.sync(
                namespace(ssh_dir, accounts=["my.1password.eu"]), op=FakeOp(ACCOUNTS, items)
            )

            self.assertEqual(result.removed, [])
            self.assertTrue((ssh_dir / "pumbaa").exists())
            self.assertTrue((ssh_dir / "neurobetter-ssh-key").exists())
            self.assertEqual(len(manifest_of(ssh_dir)["keys"]), 2)

    def test_a_failure_changes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            ssh_dir = Path(directory)
            sync.sync(
                namespace(ssh_dir),
                op=FakeOp(ACCOUNTS, [item("i1", "pumbaa", "SHA256:aaa")]),
            )
            before = (ssh_dir / "pumbaa").read_text()
            before_manifest = (ssh_dir / sync.MANIFEST_NAME).read_text()

            with self.assertRaises(sync.SyncError):
                sync.sync(
                    namespace(ssh_dir),
                    op=FakeOp(ACCOUNTS, [item("i1", "pumbaa", "SHA256:aaa")], fail_on_get=True),
                )

            self.assertEqual((ssh_dir / "pumbaa").read_text(), before)
            self.assertEqual(
                (ssh_dir / sync.MANIFEST_NAME).read_text(), before_manifest
            )

    def test_skips_an_item_that_has_no_private_key(self):
        with tempfile.TemporaryDirectory() as directory:
            ssh_dir = Path(directory)
            broken = item("i1", "Broken", "SHA256:aaa")
            broken["fields"] = [
                field for field in broken["fields"] if field["id"] != "private_key"
            ]
            result = sync.sync(namespace(ssh_dir), op=FakeOp(ACCOUNTS, [broken]))

            self.assertEqual(result.key_count, 0)
            self.assertTrue(any("Broken" in warning for warning in result.warnings))
            self.assertFalse((ssh_dir / "broken").exists())

    def test_a_renamed_item_keeps_its_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            ssh_dir = Path(directory)
            sync.sync(
                namespace(ssh_dir),
                op=FakeOp(ACCOUNTS, [item("i1", "Old Title", "SHA256:aaa")]),
            )
            sync.sync(
                namespace(ssh_dir),
                op=FakeOp(ACCOUNTS, [item("i1", "New Title", "SHA256:aaa")]),
            )

            self.assertTrue((ssh_dir / "old-title").exists())
            self.assertFalse((ssh_dir / "new-title").exists())
            self.assertEqual(manifest_of(ssh_dir)["keys"]["old-title"]["title"], "New Title")


if __name__ == "__main__":
    unittest.main()
