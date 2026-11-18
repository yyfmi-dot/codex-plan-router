from __future__ import annotations

from pathlib import Path
import hashlib
import subprocess
import tomlkit

from .storage import atomic, read, save


def check_competing_writer(store):
    cc_settings = read(Path.home() / ".cc-switch/settings.json", {})
    cc_home = Path(cc_settings.get("codexConfigDir") or (Path.home() / ".codex")).expanduser().resolve()
    if store.codex_home().resolve() == cc_home and subprocess.run(
            ["pgrep", "-x", "cc-switch"], capture_output=True).returncode == 0:
        raise RuntimeError("请先退出 CC Switch，再启用路由；避免它覆盖 Codex 配置。账号和配置仍保留。")


def current_model(store):
    path = store.codex_home() / "config.toml"
    doc = tomlkit.parse(path.read_text() if path.exists() else "")
    return str(doc.get("model", ""))


def activate(store, model):
    from . import catalog, cc_switch
    if cc_switch.linked(store):
        cc_switch.request(store, "route/activate", {"base_url": endpoint(store),
                          "bearer": store.access()["client"], "model": model,
                          "codex_home": str(store.codex_home())}, timeout=60)
        settings = store.settings()
        settings.update(activated=True, activated_model=model)
        store.save(settings)
        return
    check_competing_writer(store)
    path = store.codex_home() / "config.toml"
    original = path.read_bytes() if path.exists() else b""
    doc = tomlkit.parse(original.decode())
    backup = store.data / "config-before-activation.toml"
    if not backup.exists():
        atomic(backup, original)
    providers = doc.setdefault("model_providers", {})
    providers["custom"] = {
        "name": "Plan Router", "base_url": endpoint(store), "wire_api": "responses",
        "requires_openai_auth": False, "experimental_bearer_token": store.access()["client"],
        "supports_websockets": False,
    }
    doc["model_provider"] = "custom"
    doc["model"] = model
    # Retire only the known CC Switch-generated catalog, never a user's own catalog.
    old_catalog = doc.get("model_catalog_json")
    retired_catalog = bool(old_catalog and Path(str(old_catalog)).name == "cc-switch-model-catalog.json")
    if retired_catalog:
        del doc["model_catalog_json"]
    if catalog.client_path(store).exists():
        doc["model_catalog_json"] = str(catalog.client_path(store))
    if path.exists() and path.read_bytes() != original:
        raise RuntimeError("Codex 配置正在被其他程序修改；本次未覆盖，请重试。")
    atomic(path, tomlkit.dumps(doc).encode())
    settings = store.settings()
    settings.update(activated=True, activated_model=model, retired_catalog=retired_catalog)
    store.save(settings)


def endpoint(store):
    return "http://127.0.0.1:%s/v1" % store.settings()["gateway_port"]


def is_active(store):
    path = store.codex_home() / "config.toml"
    try:
        doc = tomlkit.parse(path.read_text())
        provider = doc.get("model_providers", {}).get("custom", {})
        return (doc.get("model_provider") == "custom" and provider.get("base_url") == endpoint(store)
                and provider.get("experimental_bearer_token") == store.access()["client"])
    except Exception:
        return False


def restore(store):
    from . import catalog, cc_switch
    if cc_switch.linked(store):
        if not store.settings().get("activated"):
            return {"restored": False, "reason": "此前已恢复连接。"}
        result = cc_switch.request(store, "route/restore", {}, timeout=60)
        settings = store.settings()
        settings["activated"] = False
        store.save(settings)
        return result
    path = store.codex_home() / "config.toml"
    backup = store.data / "config-before-activation.toml"
    if not backup.exists():
        return {"restored": False, "reason": "尚未启用，无需恢复。"}
    if not is_active(store):
        if not store.settings().get("activated"):
            return {"restored": False, "reason": "此前已恢复连接；不会覆盖当前配置。"}
        raise RuntimeError("当前配置已由其他工具接管；未覆盖你的改动。")
    original = tomlkit.parse(backup.read_text())
    doc = tomlkit.parse(path.read_text())
    for key in ("model_provider",):
        if key in original:
            doc[key] = original[key]
        elif key in doc:
            del doc[key]
    old_provider = original.get("model_providers", {}).get("custom")
    if old_provider is None:
        del doc["model_providers"]["custom"]
        if not doc["model_providers"] and "model_providers" not in original:
            del doc["model_providers"]
    else:
        doc["model_providers"]["custom"] = old_provider
    if doc.get("model") == store.settings().get("activated_model"):
        if "model" in original:
            doc["model"] = original["model"]
        else:
            del doc["model"]
    if doc.get("model_catalog_json") == str(catalog.client_path(store)):
        if "model_catalog_json" in original:
            doc["model_catalog_json"] = original["model_catalog_json"]
        else:
            del doc["model_catalog_json"]
    if store.settings().get("retired_catalog") and "model_catalog_json" not in doc:
        if "model_catalog_json" in original:
            doc["model_catalog_json"] = original["model_catalog_json"]
    atomic(path, tomlkit.dumps(doc).encode())
    settings = store.settings()
    settings["activated"] = False
    store.save(settings)
    return {"restored": True}
