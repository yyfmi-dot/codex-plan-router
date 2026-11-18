#!/usr/bin/env python3
"""Install the packaged local marketplace, then run its onboarding controller."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

BASE = Path(__file__).resolve().parent
PAYLOAD = BASE / "plugins/codex-plan-router"
sys.path[:0] = [str(PAYLOAD / "scripts"), str(PAYLOAD / "scripts/vendor")]
from cpr.storage import atomic
from cpr.host import native_cli


def install_companion():
    metadata = json.loads((BASE / "companion.json").read_text())
    if platform.machine() != metadata["architecture"]:
        raise RuntimeError("这个 CC Switch 联动安装包适用于 Apple Silicon；Intel 版尚未发布。")
    archive = BASE / metadata["file"]
    if hashlib.sha256(archive.read_bytes()).hexdigest() != metadata["sha256"]:
        raise RuntimeError("CC Switch 配套包校验失败，未安装。")
    target = Path.home() / "Applications/CC Switch Plan Router.app"
    marker = target / "Contents/Resources/plan-router-companion.json"
    already_current = marker.exists() and json.loads(marker.read_text()).get("build") == metadata["build"]
    processes = subprocess.run(["pgrep", "-x", "cc-switch"], capture_output=True, text=True)
    running = processes.returncode == 0
    own_running = False
    if running:
        for pid in processes.stdout.split():
            command = subprocess.run(["ps", "-p", pid, "-o", "command="], capture_output=True, text=True).stdout
            own_running |= str(target / "Contents/MacOS/cc-switch") in command
    if running and not (already_current and own_running):
        raise RuntimeError("请先保存 CC Switch 中的编辑，并从它的菜单选择退出，再双击本安装文件。只需退出一次，原账号会继续保留。")
    if not already_current:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            info = plistlib.loads((target / "Contents/Info.plist").read_bytes())
            if info.get("CFBundleIdentifier") != metadata["bundle_id"] or not marker.exists():
                raise RuntimeError("目标应用目录不是我们的联动版，未覆盖。")
        with tempfile.TemporaryDirectory(prefix=".plan-router-install-", dir=target.parent) as temporary:
            stage = Path(temporary)
            subprocess.run(["ditto", "-x", "-k", str(archive), str(stage)], check=True, capture_output=True)
            incoming = stage / target.name
            info = plistlib.loads((incoming / "Contents/Info.plist").read_bytes())
            if info.get("CFBundleIdentifier") != metadata["bundle_id"]:
                raise RuntimeError("配套应用标识校验失败。")
            subprocess.run(["codesign", "--verify", "--deep", "--strict", str(incoming)], check=True, capture_output=True)
            backup = target.with_name("CC Switch Plan Router.previous.app")
            if target.exists():
                if backup.exists():
                    shutil.rmtree(backup)
                target.rename(backup)
            try:
                incoming.rename(target)
            except Exception:
                if backup.exists() and not target.exists():
                    backup.rename(target)
                raise
    subprocess.run(["open", "-g", str(target)], check=True, capture_output=True)
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--register-only", action="store_true", help="仅注册插件，不启动首次设置")
    parser.add_argument("--codex-home")
    parser.add_argument("--destination")
    parser.add_argument("--codex-cli")
    parser.add_argument("--plugin-only", action="store_true", help="仅安装插件；独立管理账号，不安装 CC Switch 配套版")
    args = parser.parse_args()
    if platform.system() != "Darwin" or sys.version_info < (3, 9):
        raise RuntimeError("首版需要 macOS、Python 3.9+。")
    cli = native_cli(args.codex_cli)
    companion = None
    if not args.register_only and not args.plugin_only:
        print("正在安装 CC Switch 联动版，继续使用你现有的账号库…", flush=True)
        companion = install_companion()
    destination = Path(args.destination or (Path.home() / ".local/share/codex-plan-router/marketplace")).expanduser().resolve()
    codex_home = Path(args.codex_home or os.environ.get("CODEX_HOME") or (Path.home() / ".codex")).expanduser().resolve()
    identity = json.loads((PAYLOAD / "plugin.json").read_text())
    assert identity["name"] == "codex-plan-router"
    target = destination / "plugins/codex-plan-router"
    if target.exists() and not (target / "plugin.json").exists():
        raise RuntimeError("安装目录里有其他文件，未覆盖。请更换 --destination。")
    if (target / "plugin.json").exists():
        if json.loads((target / "plugin.json").read_text()).get("name") != "codex-plan-router":
            raise RuntimeError("该安装目录由其他插件使用，未覆盖。")
    shutil.copytree(PAYLOAD, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    marketplace = {
        "name": "codex-plan-router-local",
        "interface": {"displayName": "Codex Plan Router 本机插件"},
        "plugins": [{
            "name": "codex-plan-router",
            "source": {"source": "local", "path": "./plugins/codex-plan-router"},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": "Productivity",
        }],
    }
    atomic(destination / ".agents/plugins/marketplace.json",
           (json.dumps(marketplace, ensure_ascii=False, indent=2) + "\n").encode())
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    print("正在注册 Codex 插件…", flush=True)
    result = subprocess.run([str(cli), "plugin", "marketplace", "add", str(destination), "--json"],
                            env=env, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Codex 未接受插件源；请确认客户端版本并重试。你的模型路由未修改。")
    result = subprocess.run(
        [str(cli), "plugin", "add", "codex-plan-router@codex-plan-router-local", "--json"],
        env=env, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("插件源已注册，但原生安装未完成；请在 Codex 插件目录中选择该插件并安装。")
    print("插件已通过 Codex 原生命令安装。重新打开 Codex 后可看到 Codex Plan Router。", flush=True)
    if not args.register_only:
        print("正在准备本机路由，完成后可在设置页查看联动账号并启用…", flush=True)
        result = subprocess.run([sys.executable, str(target / "scripts/router.py"), "setup",
                                 "--codex-home", str(codex_home), "--source", "cc-switch" if companion else "local"], env=env)
        if result.returncode:
            raise RuntimeError("插件已注册，路由设置暂未完成。可在 Codex 内点击插件的“运行设置”继续。")
    print("安装完成。确认账号、选择默认模型并启用路由后，请重启 Codex 一次。", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("安装未完成：" + str(error), file=sys.stderr)
        sys.exit(1)
