"""Real supervisor/engine against a loopback CC contract fixture; no real secrets."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import base64
import hashlib
import json
import shutil
import sys
import tempfile
import threading
import time
import urllib.request

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE / "plugin/scripts"), str(BASE / "plugin/scripts/vendor")]
from cpr import cc_switch, engine
from cpr.cli import setup, stop, ready
from cpr.controller import Controller
from cpr.storage import Store, save, read

fixture = {"generation": 1, "removed": False, "key": "sk-test-" + "a" * 60, "plan_calls": 0}
bridge_token = "fixture-only-bridge-" + "z" * 44

with tempfile.TemporaryDirectory(prefix="cc-linked-router-") as temporary:
    root = Path(temporary)
    codex_home = root / "codex"
    codex_home.mkdir()
    cc_home = root / "cc-switch"
    store = Store(root / "router")
    class Bridge(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, result):
            body = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            assert self.headers.get("Authorization") == "Bearer " + bridge_token
            assert self.headers.get("Origin") is None
            self.send({"schema": 1, "version": "fixture", "codex_home": str(codex_home),
                       "accounts": [] if fixture["removed"] else [{"id": "plan", "label": "Linked Plan", "revision": 1}],
                       "keys": [] if fixture["removed"] else [{"id": "api", "label": "Linked API",
                                 "revision": hashlib.sha256(fixture["key"].encode()).hexdigest()}]})

        def do_POST(self):
            assert self.headers.get("Authorization") == "Bearer " + bridge_token
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if self.path.endswith("/plan"):
                fixture["plan_calls"] += 1
                expires = int(time.time()) + (90 if fixture["generation"] == 1 else 3600)
                claims = {"exp": expires, "https://api.openai.com/auth": {"chatgpt_plan_type": "pro", "chatgpt_account_id": "workspace-fixture"}}
                access = "e30." + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=") + ".fixture-" + str(fixture["generation"])
                self.send({"id": "plan", "access_token": access, "id_token": "fixture-id", "account_id": "workspace-fixture",
                           "expires_at": expires, "last_refresh": datetime.now(timezone.utc).isoformat()})
            else:
                self.send({"id": "api", "key": fixture["key"], "base_url": "https://api.openai.com/v1"})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Bridge)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    save(cc_home / "plan-router-bridge/connection.json", {"schema": 1, "host": "127.0.0.1",
         "port": server.server_port, "token": bridge_token})
    old = Path((BASE / "dist/smoke-path").read_text()) / "router/bin/8.0.76/cli-proxy-api"
    target = engine.binary(store)
    target.parent.mkdir(parents=True)
    shutil.copy2(old, target)
    target.chmod(0o700)
    target.with_suffix(".sha256").write_text(hashlib.sha256(target.read_bytes()).hexdigest())

    def wait(predicate, timeout=20):
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if predicate():
                return True
            time.sleep(0.2)
        return False

    checks = {}
    try:
        setup(store, str(codex_home), no_service=True, no_browser=True, source="cc-switch", cc_switch_home=str(cc_home))
        checks["cc_account_discovered_by_real_engine"] = wait(lambda: bool(Controller(store).status()["accounts"]))
        checks["cc_api_key_live_reloaded"] = wait(lambda: bool(Controller(store).status()["api_keys"]))
        assert all(checks.values()), checks
        file = next(store.auths.glob("cc-*.json"))
        first_access = read(file)["access_token"]
        fixture["generation"] = 2
        checks["access_lease_renews_without_refresh_secret"] = wait(lambda: file.exists() and read(file)["access_token"] != first_access)
        checks["projected_file_excludes_refresh_token"] = "refresh_token" not in file.read_text()
        checks["no_keys_in_status"] = fixture["key"] not in json.dumps(Controller(store).status())
        checks["linked_mode_rejects_second_credential_writer"] = False
        try:
            Controller(store).dispatch("key-add", {"key": fixture["key"], "label": "duplicate"})
        except ValueError:
            checks["linked_mode_rejects_second_credential_writer"] = True
        engine.set_mode(store, "api-only")
        checks["mode_disables_linked_plan"] = wait(lambda: all(x.get("disabled") for x in Controller(store).status()["accounts"]))
        engine.set_mode(store, "plan-first")
        checks["mode_reenables_linked_plan"] = wait(lambda: all(not x.get("disabled") for x in Controller(store).status()["accounts"]))
        hold = BASE / ".build/keep-ui-fixture"
        if hold.exists():
            save(BASE / ".build/cc-ui-session.json", {"root": str(store.root)})
            while hold.exists():
                time.sleep(0.2)
        fixture["removed"] = True
        checks["cc_deletion_removes_engine_plan_and_api"] = wait(lambda: not Controller(store).status()["accounts"] and not Controller(store).status()["api_keys"])
        checks["native_codex_config_untouched_until_activation"] = not (codex_home / "config.toml").exists()
        assert all(checks.values()), checks
        (BASE / "dist/cc-service-verification.json").write_text(json.dumps(checks, indent=2) + "\n")
        print(json.dumps(checks))
    finally:
        stop(store)
        wait(lambda: not ready(store))
        server.shutdown()
        server.server_close()
