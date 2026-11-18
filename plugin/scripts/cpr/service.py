from __future__ import annotations

from pathlib import Path
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import secrets
import signal

from . import catalog, cc_switch, codex, engine
from .controller import Controller
from .history import History
from .storage import lock, save


def serve(store):
    def terminate(*_):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, terminate)
    with lock(store.data / "service.lock", blocking=False):
        cc_switch.prepare(store)
        if cc_switch.linked(store):
            cc_switch.launch_companion(store)
        process = engine.start(store)
        save(store.data / "service-process.json", {"pid": os.getpid(), "engine_pid": process.pid})
        engine_failed = threading.Event()
        try:
            if store.settings().get("mode") == "api-only":
                engine.set_mode(store, "api-only")
            controller = Controller(store)
            settings = store.settings()
            origin = "http://127.0.0.1:%s" % settings["ui_port"]
            ui_root = Path(__file__).resolve().parent.parent / "ui"
            stopping = threading.Event()
            synchronizer = cc_switch.Sync(store) if cc_switch.linked(store) else None

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *_):
                    pass

                def respond(self, code, content, kind="application/json"):
                    if isinstance(content, (dict, list)):
                        content = json.dumps(content, ensure_ascii=False).encode()
                    self.send_response(code)
                    self.send_header("Content-Type", kind)
                    self.send_header("Content-Length", str(len(content)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("Referrer-Policy", "no-referrer")
                    self.send_header("Content-Security-Policy",
                                     "default-src 'none'; script-src 'self'; style-src 'self'; "
                                     "connect-src 'self'; img-src 'self'; base-uri 'none'; "
                                     "frame-ancestors 'none'; form-action 'self'")
                    self.end_headers()
                    self.wfile.write(content)

                def allowed(self, authenticated=True):
                    if self.headers.get("Host") != origin.split("//", 1)[1]:
                        self.respond(403, {"error": "不接受此 Host。"})
                        return False
                    if self.headers.get("Origin") not in (None, origin):
                        self.respond(403, {"error": "不接受跨站请求。"})
                        return False
                    expected = "Bearer " + store.access()["ui"]
                    if authenticated and not secrets.compare_digest(
                            self.headers.get("Authorization", ""), expected):
                        self.respond(401, {"error": "请从插件重新打开设置页面。"})
                        return False
                    return True

                def do_GET(self):
                    route = self.path.split("?", 1)[0]
                    if not self.allowed(authenticated=route.startswith("/api/")):
                        return
                    if route == "/api/status":
                        self.respond(200, controller.status())
                    elif route == "/api/models":
                        self.respond(200, {"models": catalog.model_ids(store)})
                    elif route in ("/", "/app.js", "/style.css"):
                        file = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}[route]
                        kind = {"/": "text/html; charset=utf-8", "/app.js": "text/javascript; charset=utf-8",
                                "/style.css": "text/css; charset=utf-8"}[route]
                        self.respond(200, (ui_root / file).read_bytes(), kind)
                    else:
                        self.respond(404, {"error": "页面不存在。"})

                def do_POST(self):
                    if not self.allowed():
                        return
                    try:
                        length = int(self.headers.get("Content-Length", "-1"))
                        if length < 0 or length > 16384:
                            raise ValueError("请求长度无效。")
                        value = json.loads(self.rfile.read(length))
                        if not isinstance(value, dict):
                            raise ValueError("请求格式无效。")
                        action = self.path.removeprefix("/api/")
                        result = catalog.refresh(store) if action == "models-refresh" else controller.dispatch(action, value)
                        self.respond(200, result)
                    except (ValueError, RuntimeError) as error:
                        self.respond(400, {"error": str(error)})
                    except Exception:
                        self.respond(500, {"error": "操作失败，未输出凭据。请在插件中运行诊断。"})

            server = ThreadingHTTPServer(("127.0.0.1", settings["ui_port"]), Handler)
            server.daemon_threads = True

            def history_worker():
                generation, complete = None, False
                while not stopping.is_set():
                    try:
                        latest = store.settings()
                        if latest.get("history_generation") != generation:
                            generation, complete = latest.get("history_generation"), False
                        if latest.get("history_enabled") and not complete and codex.is_active(store):
                            result = History(store).run()
                            complete = result.get("pending") == 0
                    except Exception as error:
                        save(store.data / "history-status.json",
                             {"error": "历史统一暂未完成：" + type(error).__name__,
                              "pending": True})
                    stopping.wait(30)

            threading.Thread(target=history_worker, daemon=True).start()
            def catalog_worker():
                if not store.settings().get("catalog_updates", True):
                    return
                if catalog.prepare(store).get("source") == "bundled":
                    catalog.refresh(store)
                while not stopping.wait(catalog.POLL_SECONDS):
                    catalog.refresh(store)
            threading.Thread(target=catalog_worker, daemon=True).start()
            def source_worker():
                try:
                    while not stopping.is_set():
                        try:
                            synchronizer.tick()
                        except Exception:
                            # No upstream payloads, tokens or headers in diagnostics.
                            synchronizer.checked = 0
                            with lock(store.lock_path):
                                cc_switch.prepare(store)
                                engine.render(store)
                            save(store.data / "cc-switch-status.json", {"connected": False, "checked_at": 0})
                        stopping.wait(1)
                finally:
                    synchronizer.close()
            if synchronizer:
                threading.Thread(target=source_worker, daemon=True).start()
            def watch_engine():
                while not stopping.wait(0.5):
                    if process.poll() is not None:
                        engine_failed.set()
                        server.shutdown()
                        return
            threading.Thread(target=watch_engine, daemon=True).start()
            try:
                server.serve_forever(poll_interval=0.5)
            finally:
                stopping.set()
                server.server_close()
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except Exception:
                process.kill()
                process.wait()
        if engine_failed.is_set():
            raise RuntimeError("路由子进程退出，后台服务将重新启动。")
