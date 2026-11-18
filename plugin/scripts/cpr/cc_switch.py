"""CC Switch is the credential/config owner; these are disposable access leases."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import stat
import subprocess
import time
import urllib.error
import urllib.request

from .storage import lock, read, save

POLL_SECONDS = 5
SOURCE_TTL = 30
RENEW_BEFORE = 120
EXPIRY_MARGIN = 15
RETRY_SECONDS = 60
PLAN_PRIORITY = 100
DEFAULT_PLAN_PRIORITY = 200


def launch_companion(store):
    if store.settings().get("cc_switch_home") and not store.settings().get("companion_app"):
        # A custom source may belong to another installation or an isolated test.
        return False
    candidates = [Path(store.settings()["companion_app"])] if store.settings().get("companion_app") else [
        Path.home() / "Applications/CC Switch Plan Router.app", Path("/Applications/CC Switch Plan Router.app")]
    for app in candidates:
        if (app / "Contents/Resources/plan-router-companion.json").is_file():
            subprocess.run(["open", "-g", str(app)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            return True
    return False


def linked(store):
    return store.settings().get("credential_source") == "cc-switch"


def connection_path(store):
    return Path(store.settings().get("cc_switch_home") or (Path.home() / ".cc-switch")) / "plan-router-bridge/connection.json"


def request(store, path, value=None, timeout=5):
    try:
        file = connection_path(store)
        info = file.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise RuntimeError("CC Switch 桥接文件权限无效。")
        connection = json.loads(file.read_text())
        port = connection.get("port")
        if (connection.get("schema") != 1 or connection.get("host") != "127.0.0.1"
                or not isinstance(port, int) or not 1024 < port < 65536
                or not isinstance(connection.get("token"), str) or len(connection["token"]) < 40):
            raise RuntimeError("CC Switch 桥接协议不受支持。")
        req = urllib.request.Request(
            "http://127.0.0.1:%s/v1/%s" % (port, path),
            data=None if value is None else json.dumps(value).encode(),
            headers={"Authorization": "Bearer " + connection["token"], "Content-Type": "application/json"})
        # Loopback traffic must never use an environment HTTP proxy.
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as response:
            data = response.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise RuntimeError("CC Switch 桥接响应过大。")
            return json.loads(data)
    except urllib.error.HTTPError as error:
        codes = {"cc_direct_mode_required": "请先在 CC Switch 将 Codex 设为直连模式。",
                 "codex_home_mismatch": "插件和 CC Switch 使用了不同的 Codex 配置目录。",
                 "route_changed_elsewhere": "当前路由已在 CC Switch 改变，未覆盖你的选择。",
                 "previous_provider_missing": "原供应商已删除，请在 CC Switch 选择要恢复的供应商。",
                 "account_unavailable": "此账号暂不可用，请在 CC Switch 检查或重新认证。"}
        try:
            code = json.loads(error.read(4096)).get("error")
        except Exception:
            code = None
        raise RuntimeError(codes.get(code, "CC Switch 桥接操作失败（HTTP %s）。" % error.code)) from None
    except (OSError, ValueError, KeyError):
        raise RuntimeError("未连接 CC Switch 联动版；请启动配套应用。") from None


def source_status(store):
    value = read(store.data / "cc-switch-status.json", {})
    if time.time() - value.get("checked_at", 0) > SOURCE_TTL:
        value = dict(value, connected=False, stale=True)
    return value


def keys(store):
    value = read(store.data / "cc-switch-cache.json", {})
    return value.get("keys", []) if time.time() - value.get("checked_at", 0) < SOURCE_TTL else []


def prepare(store):
    """Never bootstrap the engine from a stale cache left by a stopped owner."""
    if linked(store):
        store.auths.mkdir(parents=True, exist_ok=True, mode=0o700)
        for path in store.auths.glob("cc-*.json"):
            path.unlink()
        save(store.data / "cc-switch-cache.json", {"keys": [], "checked_at": 0})
        save(store.data / "cc-switch-status.json", {"connected": False, "checked_at": 0})


class Sync:
    def __init__(self, store):
        self.store = store
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cc-lease")
        self.catalog = {"accounts": [], "keys": []}
        self.checked = 0
        self.next_poll = 0
        self.pending = {}
        self.pending_revision = {}
        self.revisions = {}
        self.leases = {}
        self.retry = {}
        self.api = {}
        self.errors = {}

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)

    def tick(self, now=None):
        from . import engine
        now = time.time() if now is None else now
        connected = False
        if now >= self.next_poll:
            self.next_poll = now + POLL_SECONDS
            try:
                result = request(self.store, "catalog")
                if (result.get("schema") != 1 or Path(result["codex_home"]).resolve() != self.store.codex_home().resolve()
                        or not isinstance(result.get("accounts"), list) or not isinstance(result.get("keys"), list)):
                    raise RuntimeError("CC Switch 和插件的 Codex 目录或协议不一致。")
                self.catalog, self.checked = result, now
                connected = True
            except (RuntimeError, KeyError, TypeError, ValueError):
                pass
        else:
            connected = now - self.checked < POLL_SECONDS + 1
        fresh = bool(self.checked and now - self.checked < SOURCE_TTL)
        accounts = {x["id"]: x for x in self.catalog["accounts"] if not x.get("reauth_required")} if fresh else {}
        api_catalog = {x["id"]: x for x in self.catalog["keys"]} if fresh else {}
        revisions = {identity: item.get("revision") for identity, item in accounts.items()}
        for account_id, revision in revisions.items():
            if self.revisions.get(account_id) != revision:
                self.leases.pop(account_id, None)
                self.retry.pop(("plan", account_id), None)
                self.errors.pop(("plan", account_id), None)
        self.revisions = revisions
        for identity, future in list(self.pending.items()):
            if not future.done():
                continue
            del self.pending[identity]
            kind, account_id = identity
            generation = self.pending_revision.pop(identity, None)
            try:
                result = future.result()
                if result.get("id") != account_id:
                    raise ValueError("lease_identity_mismatch")
                if kind == "plan" and account_id in accounts:
                    if generation != accounts[account_id].get("revision"):
                        continue
                    if (not isinstance(result.get("access_token"), str)
                            or not result.get("account_id") or result.get("expires_at", 0) <= now + EXPIRY_MARGIN
                            or "refresh_token" in result):
                        raise ValueError("invalid_access_lease")
                    self.leases[account_id] = result
                elif kind == "key" and account_id in api_catalog:
                    if generation != api_catalog[account_id].get("revision"):
                        continue
                    key = result.get("key", "")
                    if (not key.startswith("sk-") or result.get("base_url") != "https://api.openai.com/v1"
                            or hashlib.sha256(key.encode()).hexdigest() != api_catalog[account_id]["revision"]):
                        raise ValueError("invalid_key_lease")
                    self.api[account_id] = result
                self.errors.pop(identity, None)
            except Exception:
                self.retry[identity] = now + RETRY_SECONDS
                self.errors[identity] = "暂不可用，请在 CC Switch 检查账号"
        for kind, catalog in (("plan", accounts), ("key", api_catalog)):
            for account_id, item in catalog.items():
                identity = (kind, account_id)
                value = self.leases.get(account_id) if kind == "plan" else self.api.get(account_id)
                due = not value or (kind == "plan" and value["expires_at"] <= now + RENEW_BEFORE)
                if kind == "key" and value:
                    due = hashlib.sha256(value["key"].encode()).hexdigest() != item["revision"]
                if due and identity not in self.pending and now >= self.retry.get(identity, 0):
                    self.pending_revision[identity] = item.get("revision")
                    self.pending[identity] = self.pool.submit(request, self.store, "lease/" + kind, {"id": account_id}, 35)
        # Removal or source loss invalidates projections. Never retain a deleted
        # account just because its access token has not yet expired.
        self.leases = {k: v for k, v in self.leases.items() if k in accounts and v["expires_at"] > now + EXPIRY_MARGIN}
        self.api = {k: v for k, v in self.api.items() if k in api_catalog
                    and hashlib.sha256(v["key"].encode()).hexdigest() == api_catalog[k]["revision"]}
        with lock(self.store.lock_path):
            desired = set()
            # CC Switch lists its default account first. Preserve that preference;
            # every Plan still outranks the engine's negative API priorities.
            preferred = self.catalog["accounts"][0]["id"] if self.catalog["accounts"] else None
            for account_id, lease in self.leases.items():
                filename = "cc-" + hashlib.sha256(account_id.encode()).hexdigest()[:24] + ".json"
                desired.add(filename)
                path = self.store.auths / filename
                old = read(path, {})
                priority = DEFAULT_PLAN_PRIORITY if account_id == preferred else PLAN_PRIORITY
                # Do not rewrite unchanged files: quota cooldown state belongs to
                # the engine and must not be reset by each synchronization poll.
                if (old.get("access_token") != lease["access_token"] or old.get("email") != accounts[account_id]["label"]
                        or old.get("priority") != priority):
                    save(path, {"type": "codex", "email": accounts[account_id]["label"],
                        "account_id": lease["account_id"], "access_token": lease["access_token"],
                        "id_token": lease.get("id_token"), "expired": datetime.fromtimestamp(
                            lease["expires_at"], timezone.utc).isoformat(),
                        "last_refresh": lease["last_refresh"], "priority": priority,
                        "disabled": self.store.settings().get("mode") == "api-only"})
            for path in self.store.auths.glob("cc-*.json"):
                if path.name not in desired:
                    path.unlink()
            projected = [{"id": x["id"], "label": x["label"], "key": self.api[x["id"]]["key"]}
                         for x in self.catalog["keys"] if x["id"] in self.api]
            cached = read(self.store.data / "cc-switch-cache.json", {})
            save(self.store.data / "cc-switch-cache.json", {"keys": projected, "checked_at": self.checked if fresh else 0})
            if cached.get("keys") != projected:
                engine.render(self.store)
            save(self.store.data / "cc-switch-status.json", {
                "connected": connected, "checked_at": self.checked, "stale": not fresh,
                "linked": self.catalog.get("linked", False) if fresh else False,
                "version": self.catalog.get("version"),
                "accounts": [{"id": x["id"], "label": x["label"], "reauth_required": x.get("reauth_required", False),
                              "leased": x["id"] in self.leases,
                              "error": self.errors.get(("plan", x["id"]))} for x in self.catalog["accounts"]],
                "keys": [{"id": x["id"], "label": x["label"], "leased": x["id"] in self.api}
                         for x in self.catalog["keys"]],
            })
