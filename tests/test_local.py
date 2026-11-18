from pathlib import Path
from contextlib import contextmanager
from unittest import mock
import fcntl
import json
import os
import sqlite3
import sys
import tempfile
import unittest
import uuid

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE / "plugin/scripts"), str(BASE / "plugin/scripts/vendor")]
import tomlkit
from cpr import codex
from cpr.history import History
from cpr.storage import Store, save


@contextmanager
def connection(path):
    db = sqlite3.connect(path)
    try:
        with db:
            yield db
    finally:
        db.close()


class LocalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "codex"
        self.home.mkdir()
        self.store = Store(self.root / "router")
        self.store.data.mkdir(parents=True)
        self.store.auths.mkdir()
        self.store.save({"codex_home": str(self.home), "gateway_port": 19876, "keys": []})
        save(self.store.access_path, {"client": "local-fixture-token"})
        self.config = self.home / "config.toml"
        self.config.write_text('# Preserve this comment\nmodel="before"\nmodel_reasoning_effort="high"\n'
                               '[mcp_servers.example]\ncommand="sample"\n')
        self.auth = self.home / "auth.json"
        self.auth.write_text('{"fixture":"native-sign-in-must-not-change"}\n')
        self.native = self.auth.read_bytes()

    def tearDown(self):
        self.temp.cleanup()

    def activate(self):
        with mock.patch("cpr.codex.check_competing_writer"):
            codex.activate(self.store, "gpt-6.1-sol")

    def test_config_restore_preserves_later_unrelated_edits_and_native_auth(self):
        original = tomlkit.parse(self.config.read_text()).unwrap()
        self.activate()
        self.assertTrue(codex.is_active(self.store))
        changed = tomlkit.parse(self.config.read_text())
        changed["personality"] = "friendly"
        self.config.write_text(tomlkit.dumps(changed))
        codex.restore(self.store)
        restored = tomlkit.parse(self.config.read_text()).unwrap()
        self.assertEqual(restored.pop("personality"), "friendly")
        restored.pop("model_providers", None)
        self.assertEqual(restored, original)
        self.assertIn("# Preserve this comment", self.config.read_text())
        self.assertEqual(self.auth.read_bytes(), self.native)

    def test_reactivation_does_not_replace_original_backup(self):
        self.activate()
        first = (self.store.data / "config-before-activation.toml").read_bytes()
        self.activate()
        self.assertEqual((self.store.data / "config-before-activation.toml").read_bytes(), first)

    def test_restore_refuses_competing_configuration_owner(self):
        self.activate()
        text = self.config.read_text().replace("http://127.0.0.1:19876/v1", "https://other.example/v1")
        self.config.write_text(text)
        with self.assertRaises(RuntimeError):
            codex.restore(self.store)
        self.assertEqual(self.config.read_text(), text)

    def fixture_history(self):
        self.db = self.home / "state_5.sqlite"
        db = sqlite3.connect(self.db)
        db.execute("CREATE TABLE threads (id TEXT PRIMARY KEY,model_provider TEXT,rollout_path TEXT)")
        self.ids = [str(uuid.uuid4()) for _ in range(3)]
        self.files = []
        self.bodies = []
        for i, provider in enumerate(["openai", "openai", "custom"]):
            path = self.home / "sessions" / (self.ids[i] + ".jsonl")
            path.parent.mkdir(exist_ok=True)
            body = b'{"type":"event_msg","payload":{"message":"original history"}}\n'
            meta = {"type": "session_meta", "payload": {"id": self.ids[i], "model_provider": provider}}
            path.write_bytes((json.dumps(meta) + "\n").encode() + body)
            self.files.append(path)
            self.bodies.append(body)
            db.execute("INSERT INTO threads VALUES (?,?,?)", (self.ids[i], provider, str(path)))
        db.commit()
        db.close()

    def test_history_defers_native_writer_and_keeps_all_message_bytes(self):
        self.fixture_history()
        lockfile = self.home / "thread-writer-locks" / (self.ids[0] + ".lock")
        lockfile.parent.mkdir()
        with lockfile.open("a") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = History(self.store).run()
            self.assertEqual(result["pending"], 1)
            with connection(self.db) as db:
                self.assertEqual(db.execute("SELECT model_provider FROM threads WHERE id=?",
                                            (self.ids[0],)).fetchone()[0], "openai")
            self.assertEqual(json.loads(self.files[0].read_bytes().splitlines()[0])["payload"]["model_provider"], "openai")
        History(self.store).run()
        for path, body in zip(self.files, self.bodies):
            self.assertEqual(path.read_bytes().split(b"\n", 1)[1], body)
        with connection(self.db) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM threads WHERE model_provider='custom'").fetchone()[0], 3)
        # A later reply must survive undoing only the metadata migration.
        with self.files[0].open("ab") as stream:
            stream.write(b'{"type":"new-reply","text":"keep me"}\n')
        History(self.store).run(restore=True)
        self.assertTrue(self.files[0].read_bytes().endswith(b'{"type":"new-reply","text":"keep me"}\n'))
        with connection(self.db) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM threads WHERE model_provider='openai'").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT model_provider FROM threads WHERE id=?",
                                       (self.ids[2],)).fetchone()[0], "custom")
        self.assertTrue(list((self.store.data / "backups/history").rglob("*.sqlite")))

    def test_paginated_history_without_jsonl_is_migrated(self):
        path = self.home / "state_5.sqlite"
        thread_id = str(uuid.uuid4())
        with connection(path) as db:
            db.execute("CREATE TABLE threads (id TEXT,model_provider TEXT,rollout_path TEXT)")
            db.execute("INSERT INTO threads VALUES (?,?,?)", (thread_id, "openai", ""))
        self.assertEqual(History(self.store).run()["migrated"], 1)
        with connection(path) as db:
            self.assertEqual(db.execute("SELECT model_provider FROM threads").fetchone()[0], "custom")

    def test_compressed_history_is_explicitly_deferred(self):
        path = self.home / "state_5.sqlite"
        compressed = self.home / "fixture.jsonl.zst"
        compressed.write_bytes(b"fixture-compressed")
        with connection(path) as db:
            db.execute("CREATE TABLE threads (id TEXT,model_provider TEXT,rollout_path TEXT)")
            db.execute("INSERT INTO threads VALUES (?,?,?)",
                       (str(uuid.uuid4()), "openai", str(compressed)))
        result = History(self.store).run()
        self.assertEqual(result["unsupported_compressed"], 1)
        with connection(path) as db:
            self.assertEqual(db.execute("SELECT model_provider FROM threads").fetchone()[0], "openai")


if __name__ == "__main__":
    unittest.main()
