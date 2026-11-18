"""Actual engine reloads new model definitions; all credentials are fixtures."""
from pathlib import Path
from unittest import mock
import copy
import io
import json
import shutil
import sys
import tempfile
import time
import urllib.request

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE / "plugin/scripts"), str(BASE / "plugin/scripts/vendor")]
from cpr import catalog, codex, engine
from catalog_fixture import seed
from cpr.cli import setup, stop, ready
from cpr.controller import Controller
from cpr.storage import Store, read, save

with tempfile.TemporaryDirectory(prefix="catalog-reload-fixture-") as temporary:
    root = Path(temporary)
    home = root / "codex"
    home.mkdir()
    (home / "config.toml").write_text('model="gpt-6.2-sol"\nmodel_reasoning_effort="xhigh"\n')
    store = Store(root / "router")
    seed(store)
    target = engine.binary(store)
    target.parent.mkdir(parents=True)
    source = Path((BASE / "dist/smoke-path").read_text()) / "router/bin/8.0.76/cli-proxy-api"
    shutil.copy2(source, target)
    shutil.copy2(source.with_suffix(".sha256"), target.with_suffix(".sha256"))
    checks = {}
    try:
        setup(store, str(home), no_service=True, no_browser=True, source="local")
        Controller(store).dispatch("key-add", {"label":"fixture", "key":"sk-test-" + "x"*60})
        for _ in range(100):
            if "gpt-6.2-sol" in catalog.model_ids(store):
                break
            time.sleep(.1)
        checks["synthetic_bootstrap_model_registered"] = "gpt-6.2-sol" in catalog.model_ids(store)
        state = catalog.prepare(store)
        routing = read(Path(state["catalog"]))
        client = read(Path(state["codex-catalog"]))
        added = copy.deepcopy(next(x for x in routing["codex-pro"] if x["id"] == "gpt-6.2-sol"))
        added["id"] = "future-model-fixture"
        routing["codex-pro"].append(added)
        entry = copy.deepcopy(next(x for x in client["models"] if x["slug"] == "gpt-6.2-sol"))
        entry["slug"] = "future-model-fixture"
        client["models"].append(entry)
        real_open = urllib.request.urlopen
        def source_response(request, **kwargs):
            if request.full_url.startswith("https://raw.githubusercontent.com/router-for-me/models/"):
                data = client if request.full_url.endswith("codex_client_models.json") else routing
                return io.BytesIO(json.dumps(data).encode())
            return real_open(request, **kwargs)
        with mock.patch("urllib.request.urlopen", side_effect=source_response):
            checks["engine_accepts_directory_refresh"] = catalog.refresh(store)["ok"]
        for _ in range(100):
            if "future-model-fixture" in catalog.model_ids(store):
                break
            time.sleep(.1)
        checks["new_model_reaches_running_engine"] = "future-model-fixture" in catalog.model_ids(store)
        Controller(store).dispatch("activate", {})
        import tomlkit
        doc = tomlkit.parse((home / "config.toml").read_text())
        checks["activation_inherits_current_model_and_effort"] = doc["model"] == "gpt-6.2-sol" and doc["model_reasoning_effort"] == "xhigh"
        checks["new_model_reaches_client_selection"] = "future-model-fixture" in {x["slug"] for x in read(catalog.client_path(store))["models"]}
        Controller(store).dispatch("activate", {"model":"future-model-fixture"})
        checks["user_can_change_default_model_without_account_change"] = codex.current_model(store) == "future-model-fixture"
        Controller(store).dispatch("restore", {})
        checks["restore_returns_original_default_model"] = codex.current_model(store) == "gpt-6.2-sol"
        assert all(checks.values()), checks
        (BASE / "dist/catalog-reload-verification.json").write_text(json.dumps(checks,indent=2)+"\n")
        print(json.dumps(checks))
    finally:
        stop(store)
        for _ in range(100):
            if not ready(store):
                break
            time.sleep(.1)
