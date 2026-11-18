"""Read the actual Codex model picker catalog with no upstream inference."""
from pathlib import Path
import json
import os
import selectors
import subprocess
import sys
import tempfile
import time

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE / "plugin/scripts"), str(BASE / "plugin/scripts/vendor")]
from cpr.host import native_cli
from cpr.storage import Store, save
from cpr import catalog
from catalog_fixture import seed

cli = native_cli(os.environ.get("CODEX_ROUTER_TEST_CLI"))
with tempfile.TemporaryDirectory(prefix="native-model-picker-") as temporary:
    root = Path(temporary)
    source = Store(root / "router")
    seed(source)
    home = root / "codex"
    home.mkdir()
    save(home / "models.json", catalog.client_payload(source))
    (home / "config.toml").write_text('model="gpt-6.2-sol"\nmodel_provider="custom"\nmodel_catalog_json=' + json.dumps(str(home / "models.json")) + '\n'
        '[model_providers.custom]\nname="Model picker fixture"\nbase_url="http://127.0.0.1:45678/v1"\nwire_api="responses"\nrequires_openai_auth=false\nexperimental_bearer_token="fixture-only"\n')
    env = dict(os.environ, CODEX_HOME=str(home))
    process = subprocess.Popen([str(cli), "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, env=env, cwd=root)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    buffer = b""
    def rpc(identity, method, params):
        global buffer
        process.stdin.write((json.dumps({"id":identity, "method":method, "params":params}) + "\n").encode())
        process.stdin.flush()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                row = json.loads(raw)
                if row.get("id") == identity:
                    if "error" in row:
                        raise RuntimeError(str(row["error"]))
                    return row["result"]
            for key, _ in selector.select(.2):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    raise RuntimeError("Native model catalog could not be loaded")
                buffer += data
        raise TimeoutError(method)
    try:
        rpc(0, "initialize", {"clientInfo":{"name":"model_picker_verification","version":"fixture"},"capabilities":{"experimentalApi":True}})
        process.stdin.write(b'{"method":"initialized","params":{}}\n');process.stdin.flush()
        models = rpc(1, "model/list", {"includeHidden":False})
        rows = models.get("data", [])
        ids = {x.get("id") for x in rows}
        report = {"synthetic_catalog":True,"native_model_picker_has_multiple_choices":len(rows) > 1,
                  "native_model_picker_has_6_2_sol":"gpt-6.2-sol" in ids,
                  "native_model_picker_has_6_1_sol":"gpt-6.1-sol" in ids,
                  "model_count":len(rows)}
        assert all(report.values()), report
        suffix = "desktop" if os.environ.get("CODEX_ROUTER_TEST_CLI") else "vscode"
        (BASE / ("dist/model-picker-" + suffix + ".json")).write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(report))
    finally:
        selector.close()
        process.stdin.close()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate();process.wait(timeout=5)
