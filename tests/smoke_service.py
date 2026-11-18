"""Real service + HTTP tests in an isolated CODEX_HOME, no real credentials."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
import signal
import urllib.error
import urllib.request

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE / "plugin/scripts"), str(BASE / "plugin/scripts/vendor")]
import tomlkit
from cpr.cli import ready, setup, stop, plist
from cpr.storage import Store

work = Path((BASE / "dist/smoke-path").read_text())
store = Store(work / "router")
if not ready(store):
    setup(store, no_service=True, no_browser=True)
access = store.access()
origin = "http://127.0.0.1:%s" % store.settings()["ui_port"]


def call(path, body=None, auth=True, origin_header=None, host=None):
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = "Bearer " + access["ui"]
    if origin_header:
        headers["Origin"] = origin_header
    if host:
        headers["Host"] = host
    request = urllib.request.Request(origin + path, headers=headers,
                                    data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


checks = {}
try:
    for old in json.loads(call("/api/status")[1]).get("api_keys", []):
        call("/api/key-remove", {"id": old["id"]})
    checks["unauthenticated_status_rejected"] = call("/api/status", auth=False)[0] == 401
    checks["cross_origin_rejected"] = call("/api/status", origin_header="https://example.com")[0] == 403
    checks["dns_rebinding_host_rejected"] = call("/api/status", host="attacker.example")[0] == 403
    page = call("/", auth=False)
    checks["settings_page_served"] = page[0] == 200 and b"Codex Plan Router" in page[1]
    login_code, login_body = call("/api/login", {})
    login = json.loads(login_body)
    checks["independent_oauth_flow_starts"] = login_code == 200 and login.get("url", "").startswith("https://auth.openai.com/") and bool(login.get("state"))
    dummy = "sk-" + "a" * 64
    code, body = call("/api/key-add", {"label": "Fixture API", "key": dummy})
    checks["key_saved_privately"] = code == 200 and (store.settings_path.stat().st_mode & 0o777) == 0o600
    for _ in range(50):
        model_reply = call("/api/models")
        available = json.loads(model_reply[1]).get("models", [])
        if "gpt-6.1-sol" in available:
            break
        time.sleep(0.1)
    checks["engine_config_live_reload"] = "gpt-6.1-sol" in available
    checks["status_redacts_credentials"] = dummy.encode() not in call("/api/status")[1]
    checks["unsupported_model_not_silently_replaced"] = call("/api/activate", {"model": "nonexistent-model"})[0] == 400
    code, body = call("/api/activate", {"model": "gpt-6.1-sol"})
    checks["activate_isolated_codex"] = code == 200
    if code != 200:
        raise RuntimeError("Activation failed: " + body.decode())
    config = store.codex_home() / "config.toml"
    doc = tomlkit.parse(config.read_text())
    checks["custom_provider_selected"] = doc["model_provider"] == "custom"
    checks["native_auth_file_untouched"] = not (store.codex_home() / "auth.json").exists()
    doc["personality"] = "friendly"
    config.write_text(tomlkit.dumps(doc))
    code, _ = call("/api/restore", {"restore_history": True})
    restored = tomlkit.parse(config.read_text())
    checks["restore_keeps_later_settings"] = code == 200 and restored["personality"] == "friendly" and "model_provider" not in restored
    checks["restore_idempotent"] = call("/api/restore", {"restore_history": True})[0] == 200
    # Refresh the installed runtime from final source, then exercise actual launchd.
    stop(store)
    for _ in range(100):
        if not ready(store):
            break
        time.sleep(0.1)
    checks["supervisor_stops_child"] = not ready(store)
    result = setup(store, no_browser=True)
    checks["launch_agent_installed_and_ready"] = ready(store) and plist(store).exists()
    child = json.loads((store.data / "service-process.json").read_text())
    os.kill(child["engine_pid"], signal.SIGTERM)
    for _ in range(200):
        latest = json.loads((store.data / "service-process.json").read_text())
        if latest["pid"] != child["pid"] and ready(store):
            break
        time.sleep(0.1)
    checks["launch_agent_recovers_engine_crash"] = latest["pid"] != child["pid"] and ready(store)
    checks["setup_is_idempotent"] = setup(store, no_browser=True)["local_service"]
    stop(store)
    for _ in range(100):
        if not ready(store):
            break
        time.sleep(0.1)
    checks["launch_agent_stopped"] = not ready(store)
    if plist(store).exists():
        plist(store).unlink()
    assert all(checks.values()), checks
    (BASE / "dist/service-verification.json").write_text(json.dumps(checks, indent=2) + "\n")
    print(json.dumps(checks))
finally:
    stop(store)
    if plist(store).exists():
        plist(store).unlink()
