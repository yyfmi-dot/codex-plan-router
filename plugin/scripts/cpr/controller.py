from __future__ import annotations

import json
import secrets
import urllib.parse

from . import catalog, cc_switch, codex, engine
from .history import History
from .storage import lock, read


class Controller:
    def __init__(self, store):
        self.store = store

    def status(self):
        settings = self.store.settings()
        running, accounts = False, []
        try:
            files = engine.management(self.store, "credentials").get("files", [])
            running = True
            for item in files:
                accounts.append({key: item.get(key) for key in
                                 ("name", "email", "status", "disabled", "requires_sign_in",
                                  "recovery_stage", "next_retry_after")})
        except RuntimeError:
            pass
        return {
            "version": settings.get("version"), "running": running,
            "active": codex.is_active(self.store), "mode": settings.get("mode", "plan-first"),
            "credential_source": settings.get("credential_source", "local"),
            "cc_switch": cc_switch.source_status(self.store) if cc_switch.linked(self.store) else None,
            "accounts": accounts, "api_keys": [{"id": x["id"], "label": x["label"]}
                for x in (cc_switch.keys(self.store) if cc_switch.linked(self.store) else settings.get("keys", []))],
            "model": codex.current_model(self.store),
            "catalog": read(self.store.data / "catalog-status.json", {}),
            "history": read(self.store.data / "history-status.json", {}),
        }

    def dispatch(self, action, value):
        with lock(self.store.lock_path):
            if cc_switch.linked(self.store) and action in ("key-add", "key-remove", "login", "login-status"):
                raise ValueError("账号和 Key 由 CC Switch 统一管理，请在 CC Switch 新增、删除或重新认证。")
            if action == "key-add":
                key, label = str(value.get("key", "")).strip(), str(value.get("label", "")).strip()
                if not key.startswith("sk-") or len(key) < 30 or len(key) > 1024:
                    raise ValueError("请填写有效的 OpenAI 官方 API Key。")
                if not label or len(label) > 60:
                    raise ValueError("请填写不超过 60 字的名称。")
                settings = self.store.settings()
                keys = settings.setdefault("keys", [])
                if any(secrets.compare_digest(x["key"], key) for x in keys):
                    raise ValueError("这把 Key 已经添加。")
                keys.append({"id": secrets.token_hex(8), "label": label, "key": key})
                self.store.save(settings)
                engine.render(self.store)
                return {"saved": True}
            if action == "key-remove":
                settings = self.store.settings()
                settings["keys"] = [x for x in settings.get("keys", []) if x["id"] != value.get("id")]
                self.store.save(settings)
                engine.render(self.store)
                return {"removed": True}
            if action == "login":
                # Obtain a NEW authorization. Never copy native Codex/CC Switch refresh
                # tokens: each login then has exactly one refresh owner.
                result = engine.management(self.store, "oauth/auth-url?provider=codex&is_webui=true")
                url = result.get("url", "")
                if not url.startswith("https://auth.openai.com/"):
                    raise RuntimeError("登录服务返回了非预期的授权地址。")
                return {"url": url, "state": result.get("state")}
            if action == "login-status":
                state = str(value.get("state", ""))
                if len(state) > 1024:
                    raise ValueError("无效登录状态。")
                result = engine.management(self.store, "oauth/status?state=" + urllib.parse.quote(state, safe=""))
                # Error text can contain upstream data; expose only protocol status.
                status = result.get("status")
                if status == "ok" and self.store.settings().get("mode") == "api-only":
                    engine.set_mode(self.store, "api-only")
                return {"status": status}
            if action == "mode":
                engine.set_mode(self.store, value.get("mode"))
                return {"saved": True}
            if action == "activate":
                status = self.status()
                if not status["running"] or not (status["accounts"] or status["api_keys"]):
                    raise ValueError("请先登录一个订阅账号，或添加一把 API Key。")
                model = str(value.get("model", "")).strip() or codex.current_model(self.store)
                if model not in catalog.model_ids(self.store):
                    raise ValueError("请选择路由程序当前支持的模型；不会自动替换为其他模型。")
                if cc_switch.linked(self.store):
                    bridge = cc_switch.request(self.store, "catalog")
                    if "native-model-catalog" not in bridge.get("features", []):
                        raise RuntimeError("请先安装配套的新版 CC Switch 联动版，以同步 Codex 模型选择列表。")
                catalog.install_client(self.store)
                codex.activate(self.store, model)
                # The daemon retries leased, active threads after their owners exit.
                settings = self.store.settings()
                settings["history_enabled"] = True
                settings["history_generation"] = secrets.token_hex(12)
                self.store.save(settings)
                return {"activated": True, "restart_required": True}
            if action == "restore":
                result = codex.restore(self.store)
                settings = self.store.settings()
                settings["history_enabled"] = False
                self.store.save(settings)
                if value.get("restore_history"):
                    result["history"] = History(self.store).run(restore=True)
                return result
            if action == "history":
                if not codex.is_active(self.store):
                    raise ValueError("请先启用路由，再统一历史。")
                return History(self.store).run()
            raise ValueError("不支持的操作。")
