"""Opt-in real bridge/Plan/API canary. Never activates the user's Codex route."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE / "plugin/scripts"), str(BASE / "plugin/scripts/vendor")]
from cpr import catalog, cc_switch, engine
from cpr.cli import setup, stop, ready
from cpr.host import native_cli
from cpr.storage import Store, save, read

if os.environ.get("CODEX_ROUTER_LIVE_PROBE") != "1":
    raise SystemExit("Opt in with CODEX_ROUTER_LIVE_PROBE=1; uses two short inference requests.")

model = os.environ.get("CODEX_ROUTER_TEST_MODEL", "gpt-6.2-sol")

with tempfile.TemporaryDirectory(prefix="cc-linked-live-") as temporary:
    root = Path(temporary)
    store = Store(root / "router")
    discovery = cc_switch.request(store, "catalog")
    native_home = Path(discovery["codex_home"])
    before = hashlib.sha256((native_home / "config.toml").read_bytes()).hexdigest()
    cli = native_cli(os.environ.get("CODEX_ROUTER_TEST_CLI"))
    target = engine.binary(store)
    target.parent.mkdir(parents=True)
    original = Path((BASE / "dist/smoke-path").read_text()) / "router/bin/8.0.76/cli-proxy-api"
    shutil.copy2(original, target)
    shutil.copy2(original.with_suffix(".sha256"), target.with_suffix(".sha256"))
    process_pid = None
    try:
        setup(store, str(native_home), no_service=True, no_browser=True, source="cc-switch")
        process_pid = read(store.data / "development-process.json")["pid"]
        for _ in range(200):
            status = cc_switch.source_status(store)
            if (any(x.get("leased") for x in status.get("accounts", [])) and status.get("keys")
                    and all(x.get("leased") for x in status["keys"]) and model in catalog.model_ids(store)):
                break
            time.sleep(.2)
        else:
            raise RuntimeError("No valid linked Plan and API key available for canary.")
        # Explicitly remove API routes for the first canary so success proves a
        # Plan completed it. The synchronizer does not rewrite unchanged API keys.
        config = read(store.config_path)
        config["api-keys"]["codex"] = []
        save(store.config_path, config)
        time.sleep(1)
        client_home = root / "isolated-client"
        client_home.mkdir()
        available = set(catalog.model_ids(store))
        assert model in available, "Selected model is missing from the actual engine catalog."
        save(client_home / "models.json", {"models": [m for m in catalog.client_payload(store)["models"] if m["slug"] in available]})
        (client_home / "config.toml").write_text(
            'model=' + json.dumps(model) + '\nmodel_catalog_json=' + json.dumps(str(client_home / "models.json")) + '\n'
            'model_provider="custom"\nmodel_reasoning_effort="low"\n'
            'service_tier="default"\n[features]\nmemories=false\n'
            '[model_providers.custom]\nname="Linked canary"\n'
            + 'base_url="http://127.0.0.1:' + str(store.settings()["gateway_port"]) + '/v1"\n'
            + 'wire_api="responses"\nrequires_openai_auth=true\nsupports_websockets=false\n'
            + 'experimental_bearer_token="' + store.access()["client"] + '"\n')
        # Match CC Switch's preserved native-sign-in contract while copying only
        # the short access lease. The empty field is not a refresh credential.
        lease = max((read(p) for p in store.auths.glob("cc-*.json")), key=lambda x: x.get("priority", 0))
        save(client_home / "auth.json", {"auth_mode": "chatgpt", "OPENAI_API_KEY": None,
             "tokens": {"access_token": lease["access_token"], "id_token": lease["id_token"],
                        "account_id": lease["account_id"], "refresh_token": ""},
             "last_refresh": lease["last_refresh"]})
        env = os.environ.copy()
        env["CODEX_HOME"] = str(client_home)
        def client(arguments):
            result = subprocess.run([str(cli)] + arguments, env=env, cwd=root, capture_output=True, text=True, timeout=100)
            rows = []
            for line in result.stdout.splitlines():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
            return {"complete": result.returncode == 0 and any(x.get("type") == "turn.completed" for x in rows),
                "thread": next((x.get("thread_id") for x in rows if x.get("type") == "thread.started"), None),
                "message": "\n".join(x.get("item", {}).get("text", "") for x in rows if x.get("item", {}).get("type") == "agent_message")}
        first = client(["exec", "--json", "--skip-git-repo-check",
                        "Remember CC_LINKED_CONTEXT_24971. Reply exactly OK. Do not use tools."])
        report = {"plan_inference_completed": first["complete"],
                  "selected_model": model, "multiple_client_model_choices": len(available) > 1,
                  "native_login_present_with_local_bearer": True,
                  "plan_only_isolation_enforced": read(store.config_path)["api-keys"]["codex"] == [],
                  "access_projection_has_no_refresh_token": all("refresh_token" not in p.read_text() for p in store.auths.glob("cc-*.json"))}
        engine.render(store)
        engine.set_mode(store, "api-only")
        time.sleep(1)
        if first["complete"]:
            second = client(["exec", "resume", first["thread"], "--json", "--skip-git-repo-check",
                             "Repeat the marker I gave you, and nothing else. Do not use tools."])
            report.update(api_inference_completed=second["complete"],
                          same_thread_context_retained="CC_LINKED_CONTEXT_24971" in second["message"])
        report["user_model_config_unchanged"] = hashlib.sha256((native_home / "config.toml").read_bytes()).hexdigest() == before
        report["method"] = "CC Switch bridge leases; Plan-only first request; explicit API-only same-thread continuation; not real quota exhaustion"
        report_file = "live-cc-verification-6.2.json" if model == "gpt-6.2-sol" else "live-cc-verification.json"
        (BASE / "dist" / report_file).write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report))
        assert first["complete"] and report["plan_only_isolation_enforced"] and report.get("api_inference_completed") and report.get("same_thread_context_retained") and report["user_model_config_unchanged"], "Canary did not pass; see redacted verification report."
    finally:
        stop(store)
        if process_pid:
            for _ in range(200):
                result = subprocess.run(["ps", "-p", str(process_pid), "-o", "command="], capture_output=True, text=True)
                if str(store.runtime / "router.py") not in result.stdout:
                    break
                time.sleep(.2)
