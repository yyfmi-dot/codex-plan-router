"""Persist upstream catalogs; the existing engine owns validation and routing."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import re
import time
import urllib.request

from .storage import lock, read, save

BUNDLED = Path(__file__).resolve().parent.parent / "catalog"
POLL_SECONDS = 3 * 60 * 60
MAX_BYTES = 8 * 1024 * 1024
FILENAMES = ("models.json", "codex_client_models.json")


def validate(routing, client):
    def name(value):
        return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._/-]{1,128}", value)
    if not isinstance(routing, dict) or not isinstance(client, dict):
        raise ValueError("invalid_model_catalog")
    for tier in ("codex-free", "codex-plus", "codex-team", "codex-pro"):
        entries = routing.get(tier)
        if not isinstance(entries, list) or not entries or any(not isinstance(x, dict) or not name(x.get("id")) for x in entries):
            raise ValueError("invalid_model_catalog")
    entries = client.get("models")
    if not isinstance(entries, list) or not entries:
        raise ValueError("invalid_client_catalog")
    seen = set()
    for item in entries:
        if not isinstance(item, dict) or not name(item.get("slug")) or item["slug"] in seen:
            raise ValueError("invalid_client_catalog")
        seen.add(item["slug"])
        for field in ("base_instructions", "display_name", "description", "minimal_client_version",
                      "visibility", "default_reasoning_level"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError("invalid_client_catalog")
        if not all(isinstance(item.get(k), int) and item[k] > 0 for k in ("context_window", "max_context_window")):
            raise ValueError("invalid_client_catalog")
        levels = item.get("supported_reasoning_levels")
        if not isinstance(levels, list) or not levels or item["default_reasoning_level"] not in [x.get("effort") for x in levels if isinstance(x, dict)]:
            raise ValueError("invalid_client_catalog")


def stage(store, payloads, source):
    routing, client = (json.loads(x) for x in payloads)
    validate(routing, client)
    digest = hashlib.sha256(b"\0".join(payloads)).hexdigest()
    directory = store.data / "model-catalogs" / digest
    for filename, value in zip(FILENAMES, (routing, client)):
        path = directory / filename
        if not path.exists():
            save(path, value)
    return {"generation": digest, "source": source, "updated_at": time.time(),
            "catalog": str(directory / FILENAMES[0]), "codex-catalog": str(directory / FILENAMES[1])}


def prepare(store):
    state = read(store.data / "catalog-state.json", {})
    try:
        validate(read(Path(state["catalog"])), read(Path(state["codex-catalog"])))
    except (OSError, KeyError, ValueError, TypeError):
        state = stage(store, [((BUNDLED / name).read_bytes()) for name in FILENAMES], "bundled")
        save(store.data / "catalog-state.json", state)
    return state


def sources(store):
    state = prepare(store)
    return {key: state[key] for key in ("catalog", "codex-catalog")}


def client_payload(store):
    return read(Path(prepare(store)["codex-catalog"]))


def model_ids(store):
    from . import engine
    native = {x["slug"] for x in client_payload(store)["models"] if x.get("visibility") == "list"}
    return sorted(native.intersection(engine.models(store)))


def client_path(store):
    return store.codex_home() / "codex-plan-router-models.json"


def install_client(store):
    allowed = set(model_ids(store))
    payload = {"models": [x for x in client_payload(store)["models"] if x["slug"] in allowed]}
    if not payload["models"]:
        raise ValueError("暂无可用模型，请检查账号和模型目录。")
    save(client_path(store), payload)


def refresh(store):
    from . import codex, engine
    origin = read(BUNDLED / "ORIGIN.json")
    urls = {x["name"]: x["url"] for x in origin["files"]}
    def fetch(name):
        request = urllib.request.Request(urls[name], headers={"User-Agent": "codex-plan-router"})
        with urllib.request.urlopen(request, timeout=15) as response:
            data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("catalog_too_large")
        return data
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            payloads = list(pool.map(fetch, FILENAMES))
        with lock(store.lock_path):
            previous = prepare(store)
            candidate = stage(store, payloads, "upstream")
            if candidate["generation"] != previous["generation"]:
                save(store.data / "catalog-state.json", candidate)
                try:
                    engine.render(store)
                    accepted = False
                    for _ in range(20):
                        result = engine.management(store, "models/refresh", {}, "POST")
                        if result.get("ok") and result.get("sources", {}).get("catalog") == candidate["catalog"]:
                            accepted = True
                            break
                        time.sleep(.1)
                    if not accepted:
                        raise RuntimeError("catalog_reload_timeout")
                    if codex.is_active(store):
                        install_client(store)
                except Exception:
                    save(store.data / "catalog-state.json", previous)
                    engine.render(store)
                    try:
                        engine.management(store, "models/refresh", {}, "POST")
                    except Exception:
                        pass
                    raise
            else:
                save(store.data / "catalog-state.json", dict(previous, updated_at=time.time(), source="upstream"))
        result = {"ok": True, "checked_at": time.time()}
    except Exception:
        result = {"ok": False, "checked_at": time.time(), "error": "模型目录更新失败，继续使用上次有效目录。"}
    save(store.data / "catalog-status.json", result)
    return result
