from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import plistlib
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

from . import VERSION, cc_switch, codex, engine
from .controller import Controller
from .history import History
from .host import native_cli
from .service import serve
from .storage import Store, atomic, lock, read, save


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def label(store):
    return "dev.codex-plan-router." + hashlib.sha256(str(store.root).encode()).hexdigest()[:10]


def plist(store):
    return Path.home() / "Library/LaunchAgents" / (label(store) + ".plist")


def ready(store):
    if not store.settings():
        return False
    request = urllib.request.Request(
        "http://127.0.0.1:%s/api/status" % store.settings()["ui_port"],
        headers={"Authorization": "Bearer " + store.access()["ui"]})
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return json.load(response).get("running", False)
    except Exception:
        return False


def open_settings(store, browser=True):
    if not ready(store):
        raise RuntimeError("设置服务未运行，请先运行 setup。")
    if browser:
        url = "http://127.0.0.1:%s/#%s" % (store.settings()["ui_port"], store.access()["ui"])
        webbrowser.open(url)
    return {"settings_opened": browser, "local_service": True,
            "ui_port": store.settings()["ui_port"],
            "note": ("账号自动从 CC Switch 同步，请在本机设置页选择默认模型并启用。"
                     if cc_switch.linked(store) else "请在本机设置页登录账号和填写 Key。")}


def install_service(store):
    target = plist(store)
    document = {
        "Label": label(store),
        "ProgramArguments": [sys.executable, str(store.runtime / "router.py"),
                             "--root", str(store.root), "serve"],
        "WorkingDirectory": str(store.data), "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False}, "ThrottleInterval": 10, "Umask": 63,
        "StandardOutPath": "/dev/null", "StandardErrorPath": "/dev/null",
    }
    atomic(target, plistlib.dumps(document))
    domain = "gui/" + str(os.getuid())
    subprocess.run(["launchctl", "enable", domain + "/" + label(store)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    result = subprocess.run(["launchctl", "bootstrap", domain, str(target)],
                            capture_output=True)
    if result.returncode:
        raise RuntimeError("无法注册本机后台服务，请从已登录的 macOS 桌面会话运行设置。")


def setup(store, codex_home=None, no_service=False, no_browser=False, source=None, cc_switch_home=None):
    if platform.system() != "Darwin" or sys.version_info < (3, 9):
        raise RuntimeError("此版本需要 macOS 和 Python 3.9 或更新版本。")
    native_cli()
    store.root.mkdir(parents=True, exist_ok=True, mode=0o700)
    store.root.chmod(0o700)
    store.data.mkdir(exist_ok=True, mode=0o700)
    with lock(store.lock_path):
        settings = store.settings()
        requested_source = source or settings.get("credential_source") or (
            "cc-switch" if cc_switch.connection_path(store).exists() else "local")
        if requested_source not in ("local", "cc-switch"):
            raise ValueError("不支持的凭据来源。")
        changing_source = bool(settings and settings.get("credential_source", "local") != requested_source)
        if changing_source and codex.is_active(store):
            raise RuntimeError("请先恢复现有路由，再改变账号管理方式。")
        if ready(store) and settings.get("version") == VERSION and not changing_source:
            return open_settings(store, not no_browser)
        if settings:
            stop(store)
            for _ in range(50):
                if not ready(store):
                    break
                time.sleep(0.1)
            if ready(store):
                raise RuntimeError("旧服务尚未退出；本次未替换运行文件。")
        if not settings:
            first, second = port(), port()
            while first == second:
                second = port()
            settings = {"schema": 1, "version": VERSION,
                        "codex_home": str(Path(codex_home or os.environ.get("CODEX_HOME") or
                                               (Path.home() / ".codex")).expanduser().resolve()),
                        "gateway_port": first, "ui_port": second, "mode": "plan-first",
                        "keys": [], "activated": False, "history_enabled": False}
            store.save(settings)
            save(store.access_path, {k: secrets.token_urlsafe(40) for k in ("ui", "management", "client")})
        elif codex_home and Path(codex_home).expanduser().resolve() != Path(settings["codex_home"]):
            raise RuntimeError("此安装已绑定另一个 CODEX_HOME；请使用独立的 --root。")
        settings.update(version=VERSION, credential_source=requested_source)
        if cc_switch_home:
            settings["cc_switch_home"] = str(Path(cc_switch_home).expanduser().resolve())
        store.save(settings)
        store.auths.mkdir(exist_ok=True, mode=0o700)
        source = Path(__file__).resolve().parent.parent
        if source.resolve() != store.runtime.resolve():
            shutil.copytree(source, store.runtime, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.tmp"))
        engine.download(store)
        if no_service:
            process = subprocess.Popen(
                [sys.executable, str(store.runtime / "router.py"), "--root", str(store.root), "serve"],
                start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            save(store.data / "development-process.json", {"pid": process.pid})
        else:
            # Recover a stale registration left by an interrupted prior setup.
            subprocess.run(["launchctl", "bootout", "gui/" + str(os.getuid()), str(plist(store))],
                           capture_output=True)
            install_service(store)
    for _ in range(100):
        if ready(store):
            return open_settings(store, not no_browser)
        time.sleep(0.1)
    raise RuntimeError("后台服务尚未就绪；设置未改动你的 Codex 登录或模型路由。")


def stop(store):
    if platform.system() == "Darwin" and plist(store).exists():
        domain = "gui/" + str(os.getuid())
        subprocess.run(["launchctl", "disable", domain + "/" + label(store)], capture_output=True)
        subprocess.run(["launchctl", "bootout", domain, str(plist(store))], capture_output=True)
    child = read(store.data / "development-process.json", {})
    pid = child.get("pid")
    if pid:
        # Only signal a process still running this install's actual entrypoint.
        check = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True)
        if str(store.runtime / "router.py") in check.stdout:
            os.kill(pid, signal.SIGTERM)


def main():
    parser = argparse.ArgumentParser(description="Codex Plan Router 本地插件")
    parser.add_argument("--root", help="独立的本机运行目录（测试/多实例时使用）")
    sub = parser.add_subparsers(dest="command", required=True)
    setup_parser = sub.add_parser("setup", help="准备路由程序和本机设置页面")
    setup_parser.add_argument("--codex-home")
    setup_parser.add_argument("--no-service", action="store_true", help="测试用：不注册开机启动")
    setup_parser.add_argument("--no-browser", action="store_true")
    setup_parser.add_argument("--source", choices=("cc-switch", "local"), help="由 CC Switch 联动版管理账号，或独立授权")
    setup_parser.add_argument("--cc-switch-home", help="自定义 CC Switch 数据目录")
    settings_parser = sub.add_parser("settings", help="打开凭据不会进入对话的本机设置页")
    settings_parser.add_argument("--no-browser", action="store_true")
    sub.add_parser("status", help="输出不含密钥的运行状态")
    sub.add_parser("serve", help=argparse.SUPPRESS)
    sub.add_parser("history", help="补迁当前未占用的官方会话")
    restore_parser = sub.add_parser("restore", help="恢复接管前配置，保留其他新改动")
    restore_parser.add_argument("--history", action="store_true", help="同时按备份账本还原原官方分组")
    sub.add_parser("stop", help="停止路由；先恢复配置，避免留下无效请求地址")
    sub.add_parser("uninstall", help="恢复配置并停止服务；保留凭据和恢复点")
    args = parser.parse_args()
    store = Store(args.root)
    if args.command == "setup":
        result = setup(store, args.codex_home, args.no_service, args.no_browser, args.source, args.cc_switch_home)
    elif args.command == "serve":
        serve(store)
        return
    elif not store.settings():
        result = {"installed": False}
    elif args.command == "settings":
        result = open_settings(store, not args.no_browser)
    elif args.command == "status":
        result = Controller(store).status()
    elif args.command == "history":
        result = Controller(store).dispatch("history", {})
    elif args.command == "restore":
        result = Controller(store).dispatch("restore", {"restore_history": args.history})
    else:
        if codex.is_active(store):
            raise RuntimeError("请先运行 restore --history 恢复配置，再停止或卸载。")
        history = read(store.data / "history-status.json", {})
        if args.command == "uninstall" and history.get("restored") and history.get("pending"):
            raise RuntimeError("原会话分组仍有活动线程未还原；关闭后重试 restore --history，再卸载。")
        stop(store)
        result = {"stopped": True, "private_data_preserved": True}
        if args.command == "uninstall" and plist(store).exists():
            plist(store).unlink()
    print(json.dumps(result, ensure_ascii=False))
