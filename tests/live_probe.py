"""Developer-only opt-in probe. Credentials never enter the distributable plugin."""
from pathlib import Path
from datetime import datetime, timezone
import base64
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE / "plugin/scripts"), str(BASE / "plugin/scripts/vendor")]
from cpr import engine
from cpr.cli import setup, stop, ready
from cpr.codex import activate, restore
from cpr.storage import Store, save

if os.environ.get("CODEX_ROUTER_LIVE_PROBE") != "1":
    raise SystemExit("Opt-in developer probe only.")
home = Path.home()
native = json.loads((home / ".codex/auth.json").read_text())["tokens"]
claims = json.loads(base64.urlsafe_b64decode(native["access_token"].split(".")[1] + "==="))
smoke = Path((BASE / "dist/smoke-path").read_text())
cli = Path(os.environ["CODEX_ROUTER_TEST_CLI"]) if os.environ.get("CODEX_ROUTER_TEST_CLI") else sorted((home / ".vscode/extensions").glob("openai.chatgpt-*/bin/macos-aarch64/codex"))[-1]
report = {}
with tempfile.TemporaryDirectory(prefix="codex-router-live-") as temp:
    root = Path(temp)
    ch = root / "codex"
    ch.mkdir()
    (ch / "config.toml").write_text('model="gpt-6.1-sol"\nmodel_reasoning_effort="low"\n'
                                   'service_tier="default"\n[features]\nmemories=false\n')
    store = Store(root / "router")
    target = engine.binary(store)
    target.parent.mkdir(parents=True)
    shutil.copy2(smoke / "router/bin/8.0.76/cli-proxy-api", target)
    target.chmod(0o700)
    target.with_suffix(".sha256").write_text(hashlib.sha256(target.read_bytes()).hexdigest() + "\n")
    setup(store, str(ch), no_service=True, no_browser=True)
    try:
        # Access-only temporary fixture: DO NOT copy or rotate native refresh tokens.
        save(store.auths / "live-plan.json", {
            "type": "codex", "email": "live-fixture", "account_id": native["account_id"],
            "access_token": native["access_token"], "id_token": native["id_token"],
            "expired": datetime.fromtimestamp(claims["exp"], timezone.utc).isoformat(),
            "last_refresh": datetime.now(timezone.utc).isoformat(), "priority": 100,
        })
        keys = []
        with sqlite3.connect("file:" + str(home / ".cc-switch/cc-switch.db") + "?mode=ro", uri=True) as db:
            for name, raw in db.execute(
                    "SELECT name,settings_config FROM providers WHERE app_type='codex' AND name LIKE 'OpenAI API %' ORDER BY name"):
                key = json.loads(raw).get("auth", {}).get("OPENAI_API_KEY")
                if key:
                    keys.append({"id": "live-" + str(len(keys)), "label": "API fixture " + str(len(keys)+1), "key": key})
        settings = store.settings()
        settings["keys"] = keys
        store.save(settings)
        engine.render(store)
        for _ in range(100):
            files = engine.management(store, "credentials").get("files", [])
            if any(f.get("name") == "live-plan.json" for f in files):
                break
            time.sleep(.1)
        activate(store, "gpt-6.1-sol")
        env = os.environ.copy()
        env["CODEX_HOME"] = str(ch)
        def client(args):
            proc = subprocess.run([str(cli)] + args, env=env, cwd=root, capture_output=True, text=True, timeout=100)
            rows = []
            for line in proc.stdout.splitlines():
                try: rows.append(json.loads(line))
                except ValueError: pass
            text = "\n".join(
                row.get("item", {}).get("text", "") for row in rows
                if row.get("item", {}).get("type") == "agent_message")
            error_text = proc.stdout + proc.stderr
            tags = [tag for tag in ["invalid_encrypted_content","usage_limit_reached",
                                    "insufficient_quota","invalid_api_key","401","429"]
                    if tag in error_text]
            return {"returncode": proc.returncode, "complete": any(r.get("type")=="turn.completed" for r in rows),
                    "message": text, "error_tags": tags,
                    "thread_id": next((r.get("thread_id") for r in rows if r.get("type")=="thread.started"), None)}
        first = client(["exec","--json","--skip-git-repo-check",
                        "Remember the marker ROUTER_LIVE_5812. Reply exactly OK. Do not use tools."])
        report["subscription_request_completed"] = first["complete"]
        report["subscription_error_tags"] = first["error_tags"]
        engine.set_mode(store, "api-only")
        if first["complete"]:
            second = client(["exec","resume",first["thread_id"],"--json","--skip-git-repo-check",
                             "Repeat the marker I gave you, and nothing else. Do not use tools."])
            report["same_thread_continued_via_api"] = second["complete"]
            report["context_marker_retained"] = "ROUTER_LIVE_5812" in second["message"]
            report["api_error_tags"] = second["error_tags"]
        else:
            second = client(["exec","--json","--skip-git-repo-check","Reply exactly OK. Do not use tools."])
            report["fresh_api_request_completed"] = second["complete"]
            report["api_error_tags"] = second["error_tags"]
        # Never record credentials, account identifiers, raw messages, or upstream headers.
        report["method"] = "temporary access-only subscription fixture, followed by explicit API-only mode; not real quota exhaustion"
        (BASE / ("dist/live-verification-desktop.json" if os.environ.get("CODEX_ROUTER_TEST_CLI") else "dist/live-verification.json")).write_text(json.dumps(report, indent=2)+"\n")
        print(json.dumps(report))
    finally:
        try: restore(store)
        finally:
            stop(store)
            for _ in range(100):
                if not ready(store):
                    break
                time.sleep(.1)
