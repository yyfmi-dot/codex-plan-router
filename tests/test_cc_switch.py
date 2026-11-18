"""Source lifecycle tests; no real accounts, no network requests."""
from concurrent.futures import Future
from pathlib import Path
from unittest import mock
import hashlib
import json
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE / "plugin/scripts"), str(BASE / "plugin/scripts/vendor")]
from cpr import cc_switch, codex, engine
from cpr.storage import Store, save, read


class ImmediatePool:
    def __init__(self, handler):
        self.handler = handler

    def submit(self, *args):
        future = Future()
        try:
            future.set_result(self.handler(*args[1:]))
        except Exception as error:
            future.set_exception(error)
        return future

    def shutdown(self, **_):
        pass


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "codex"
        self.home.mkdir()
        self.store = Store(self.root / "router")
        self.store.save({"credential_source": "cc-switch", "codex_home": str(self.home),
                         "gateway_port": 45678, "mode": "plan-first", "keys": []})
        self.store.auths.mkdir()
        save(self.store.access_path, {"client": "client", "management": "management"})
        self.key = "sk-test-" + "a" * 60
        self.revision = lambda: hashlib.sha256(self.key.encode()).hexdigest()
        self.catalog = {"schema": 1, "codex_home": str(self.home), "version": "fixture",
                        "accounts": [{"id": "a", "label": "Plan A", "revision": 1}],
                        "keys": [{"id": "k", "label": "API A", "revision": self.revision()}]}
        self.access = "access-generation-one"
        self.expires = 5000
        self.offline = False
        self.bad_lease = False
        self.calls = []
        self.sync = cc_switch.Sync(self.store)
        self.sync.pool.shutdown()
        self.sync.pool = ImmediatePool(self.request)
        self.patch = mock.patch("cpr.cc_switch.request", side_effect=self.request)
        self.patch.start()

    def tearDown(self):
        self.sync.close()
        self.patch.stop()
        self.temp.cleanup()

    def request(self, store, path, value=None, timeout=None):
        self.calls.append(path)
        if self.offline:
            raise RuntimeError("offline")
        if path == "catalog":
            return json.loads(json.dumps(self.catalog))
        if path == "lease/plan":
            result = {"id": "a", "access_token": self.access, "id_token": "id-fixture",
                      "account_id": "workspace", "expires_at": self.expires, "last_refresh": "fixture"}
            if self.bad_lease:
                result["refresh_token"] = "forbidden"
            return result
        if path == "lease/key":
            return {"id": "k", "key": self.key, "base_url": "https://api.openai.com/v1"}
        return {"activated": True, "restored": True}

    def tick(self, now):
        with mock.patch("cpr.cc_switch.time.time", return_value=now):
            self.sync.tick(now)

    def start(self):
        self.tick(1000)
        self.tick(1001)

    def test_sync_add_delete_rotate_and_no_refresh_token(self):
        self.start()
        file = next(self.store.auths.glob("cc-*.json"))
        self.assertNotIn("refresh_token", file.read_text())
        self.assertEqual(file.stat().st_mode & 0o777, 0o600)
        first = file.stat().st_mtime_ns
        self.tick(1006)
        self.assertEqual(file.stat().st_mtime_ns, first, "polls must preserve engine cooldowns")
        self.key = "sk-test-" + "b" * 60
        self.catalog["keys"][0]["revision"] = self.revision()
        self.tick(1011)
        self.assertEqual(read(self.store.data / "cc-switch-cache.json")["keys"], [])
        self.tick(1012)
        self.assertEqual(read(self.store.config_path)["api-keys"]["codex"][0]["keys"][0]["api-key"], self.key)
        self.catalog["accounts"] = []
        self.catalog["keys"] = []
        self.tick(1016)
        self.assertEqual(list(self.store.auths.glob("cc-*.json")), [])
        self.assertEqual(read(self.store.config_path)["api-keys"]["codex"], [])
        self.catalog["accounts"] = [{"id": "a", "label": "Plan A", "revision": 2}]
        self.tick(1021)
        self.tick(1022)
        self.assertEqual(len(list(self.store.auths.glob("cc-*.json"))), 1)

    def test_source_disconnect_expires_cache_and_reconnect_recovers(self):
        self.start()
        self.offline = True
        self.tick(1006)
        self.assertEqual(len(list(self.store.auths.glob("cc-*.json"))), 1)
        self.tick(1031)
        self.assertEqual(list(self.store.auths.glob("cc-*.json")), [])
        self.assertEqual(read(self.store.config_path)["api-keys"]["codex"], [])
        self.assertFalse(read(self.store.data / "cc-switch-status.json")["connected"])
        self.offline = False
        self.tick(1036)
        self.tick(1037)
        self.assertEqual(len(list(self.store.auths.glob("cc-*.json"))), 1)

    def test_renewal_uses_access_only_generation_and_expires_unrenewable_plan(self):
        self.expires = 1100
        self.start()
        self.access = "access-generation-two"
        self.expires = 1200
        self.tick(1002)
        self.tick(1003)
        self.assertEqual(read(next(self.store.auths.glob("cc-*.json")))["access_token"], self.access)
        self.offline = True
        self.tick(1190)
        self.assertEqual(list(self.store.auths.glob("cc-*.json")), [])

    def test_refresh_token_protocol_violation_is_rejected(self):
        self.bad_lease = True
        self.start()
        self.assertEqual(list(self.store.auths.glob("cc-*.json")), [])
        self.assertNotIn("forbidden", (self.store.data / "cc-switch-status.json").read_text())

    def test_cc_reauthentication_replaces_still_valid_access_lease(self):
        self.start()
        self.access = "new-authorization-generation"
        self.catalog["accounts"][0]["revision"] = 2
        self.tick(1006)
        self.assertEqual(list(self.store.auths.glob("cc-*.json")), [])
        self.tick(1007)
        self.assertEqual(read(next(self.store.auths.glob("cc-*.json")))["access_token"], self.access)

    def test_linked_activation_and_restore_delegate_configuration_to_cc(self):
        config = self.home / "config.toml"
        config.write_text("# original\n")
        codex.activate(self.store, "gpt-6.1-sol")
        codex.restore(self.store)
        self.assertEqual(config.read_text(), "# original\n")
        self.assertIn("route/activate", self.calls)
        self.assertIn("route/restore", self.calls)
        self.assertFalse((self.store.data / "config-before-activation.toml").exists())


if __name__ == "__main__":
    unittest.main()
