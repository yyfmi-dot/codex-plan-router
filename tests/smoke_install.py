"""Test the colleague installer against the native Codex plugin/skill loader."""
from pathlib import Path
import json
import os
import selectors
import subprocess
import sys
import tempfile
import time

BASE = Path(__file__).resolve().parents[1]
VERSION = json.loads((BASE / "plugin/plugin.json").read_text())["version"]
BUNDLE = BASE / ("dist/Codex-Plan-Router-macOS-" + VERSION)
sys.path[:0] = [str(BASE / "plugin/scripts"), str(BASE / "plugin/scripts/vendor")]
from cpr.history import History
from cpr.storage import Store
from cpr.storage import lock

cli = Path(os.environ["CODEX_ROUTER_TEST_CLI"]) if os.environ.get("CODEX_ROUTER_TEST_CLI") else sorted((Path.home() / ".vscode/extensions").glob("openai.chatgpt-*/bin/macos-aarch64/codex"))[-1]
with tempfile.TemporaryDirectory(prefix="codex-router-installer-") as folder:
    work = Path(folder)
    home = work / "codex"
    home.mkdir()
    (home / "config.toml").write_text('model="gpt-6.1-sol"\n[features]\nmemories=false\n')
    command = [sys.executable, str(BUNDLE / "install.py"), "--register-only",
               "--codex-home", str(home), "--destination", str(work / "marketplace"),
               "--codex-cli", str(cli)]
    installed = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert installed.returncode == 0, installed.stderr
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    process = subprocess.Popen([str(cli), "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, env=env, cwd=work)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    buffer, cache = b"", {}
    def rpc(id, method, params):
        global buffer
        process.stdin.write((json.dumps({"id": id, "method": method, "params": params}) + "\n").encode())
        process.stdin.flush()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                try: row = json.loads(line)
                except ValueError: continue
                if "id" in row: cache[row["id"]] = row
            if id in cache:
                row = cache.pop(id)
                if "error" in row: raise RuntimeError(method + ": " + str(row["error"]))
                return row.get("result", {})
            for key, _ in selector.select(.5):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk: raise RuntimeError("Native host exited")
                buffer += chunk
        raise TimeoutError(method)
    report = {"colleague_installer_registered": True}
    try:
        rpc(0, "initialize", {"clientInfo": {"name": "plugin_install_verification", "version": VERSION},
                              "capabilities": {"experimentalApi": True}})
        process.stdin.write(b'{"method":"initialized","params":{}}\n')
        process.stdin.flush()
        listing = rpc(1, "plugin/list", {"cwds": [str(work)]})
        details = rpc(4, "plugin/read", {"marketplacePath":str(work / "marketplace/.agents/plugins/marketplace.json"), "pluginName":"codex-plan-router"})
        (BASE / "dist/native-plugin-read-debug.json").write_text(json.dumps(details,indent=2))
        skills = rpc(2, "skills/list", {"cwds": [str(work)], "forceReload": True})
        def objects(value):
            if isinstance(value, dict):
                yield value
                for child in value.values(): yield from objects(child)
            elif isinstance(value, list):
                for child in value: yield from objects(child)
        (BASE / "dist/native-plugin-list-debug.json").write_text(json.dumps(listing,indent=2))
        (BASE / "dist/native-skills-list-debug.json").write_text(json.dumps(skills,indent=2))
        names = {d.get("name") for d in objects(skills)}
        report["native_host_discovered_setup_skill"] = "codex-plan-router:setup-router" in names
        report["native_host_discovered_manage_skill"] = "codex-plan-router:manage-router" in names
        report["native_host_discovered_plugin"] = any(
            d.get("name") == "codex-plan-router" for d in objects(listing))
        # Verify the migration's lease protocol against an actual native owner.
        started = rpc(3, "thread/start", {"modelProvider": "openai", "model": "gpt-6.1-sol",
                                         "cwd": str(work), "historyMode": "legacy"})
        thread_id = started["thread"]["id"]
        store = Store(work / "router")
        store.data.mkdir(parents=True)
        store.save({"codex_home": str(home)})
        lease = home / "thread-writer-locks" / (thread_id + ".lock")
        try:
            with History(store).native_lease(thread_id):
                report["actual_native_writer_lease_is_respected"] = False
        except BlockingIOError:
            report["actual_native_writer_lease_is_respected"] = True
        assert all(report.values()), report
    finally:
        selector.close()
        process.stdin.close()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
    with History(store).native_lease(thread_id):
        report["closed_native_thread_releases_lease"] = True
    assert all(report.values()), report
    (BASE / ("dist/install-verification-desktop.json" if os.environ.get("CODEX_ROUTER_TEST_CLI") else "dist/install-verification.json")).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
