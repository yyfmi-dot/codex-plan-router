from __future__ import annotations

from pathlib import Path
import hashlib
import io
import json
import os
import platform
import subprocess
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request

from .storage import atomic, save

SCRIPTS = Path(__file__).resolve().parent.parent


def release():
    return json.loads((SCRIPTS / "engine-release.json").read_text())


def binary(store):
    return store.root / "bin" / release()["version"] / "cli-proxy-api"


def download(store):
    if platform.system() != "Darwin":
        raise RuntimeError("此版本支持 macOS；尚未支持 Windows/Linux 安装。")
    item = release()["assets"].get(platform.machine())
    if not item:
        raise RuntimeError("不支持此 CPU 架构。")
    target = binary(store)
    digest_file = target.with_suffix(".sha256")
    if target.exists() and digest_file.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() == digest_file.read_text().strip():
            return target
        raise RuntimeError("已安装的路由程序校验失败；请重新运行设置。")
    request = urllib.request.Request(item["url"], headers={"User-Agent": "codex-plan-router/0.1"})
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read(100 * 1024 * 1024 + 1)
    if len(data) > 100 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != item["sha256"]:
        raise RuntimeError("官方路由程序下载校验失败，未运行。")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        member = next((m for m in archive.getmembers()
                       if Path(m.name).name == "cli-proxy-api" and m.isfile()), None)
        if not member or member.size > 200 * 1024 * 1024:
            raise RuntimeError("路由程序压缩包内容无效。")
        content = archive.extractfile(member).read()
        atomic(target, content, 0o700)
        atomic(digest_file, (hashlib.sha256(content).hexdigest() + "\n").encode())
        license_member = next((m for m in archive.getmembers()
                               if Path(m.name).name == "LICENSE" and m.isfile()), None)
        if license_member:
            atomic(target.parent / "LICENSE", archive.extractfile(license_member).read())
    return target


def render(store):
    from . import catalog, cc_switch
    settings, access = store.settings(), store.access()
    keys = cc_switch.keys(store) if cc_switch.linked(store) else settings.get("keys", [])
    config = {
        "config-version": 8,
        "models": catalog.sources(store),
        "server": {"host": "127.0.0.1", "port": settings["gateway_port"]},
        "management": {"allow-remote": False, "secret-key": access["management"],
                       "disable-control-panel": True},
        "access": {"api-keys": [access["client"]]},
        "oauth": {"auth-dir": str(store.auths), "auth-auto-refresh-workers": 2},
        "routing": {
            "strategy": "fill-first", "session-affinity": False,
            "retry": {"request-retry": 0, "max-retry-credentials": 0, "max-retry-interval": 0},
            "cooldown": {"disable-cooling": False, "save-cooldown-status": True},
        },
        "requests": {"streaming": {"bootstrap-retries": 9}},
        "upstream": {"codex": {"stream-bootstrap-buffering": True}},
        "api-keys": {"codex": [
            {"name": item["label"], "priority": -10 - i, "base-url": "https://api.openai.com/v1",
             "keys": [{"api-key": item["key"], "websockets": False,
                       "disable-codex-cloaking": True}]}
            for i, item in enumerate(keys)
        ]},
        "observability": {
            "logs": {"debug": False, "logging-to-file": False, "request-log": False},
            "usage": {"usage-statistics-enabled": False},
        },
    }
    save(store.config_path, config)


def management(store, path, data=None, method=None):
    url = "http://127.0.0.1:%s/v8/management/%s" % (store.settings()["gateway_port"], path)
    request = urllib.request.Request(
        url, data=None if data is None else json.dumps(data).encode(),
        headers={"Authorization": "Bearer " + store.access()["management"],
                 "Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError("路由管理请求失败（HTTP %s）。" % error.code) from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("本地路由尚未启动或暂时不可用。") from None


def models(store):
    url = "http://127.0.0.1:%s/v1/models" % store.settings()["gateway_port"]
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + store.access()["client"]})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return sorted({x["id"] for x in json.load(response).get("data", [])})
    except Exception:
        return []


def start(store):
    render(store)
    # No upstream credentials or request bodies go to inherited logs.
    process = subprocess.Popen(
        [str(binary(store)), "-local-model", "-config", str(store.config_path)],
        cwd=str(store.data), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("路由程序未能启动；请检查端口是否被占用。")
        try:
            management(store, "credentials")
            return process
        except RuntimeError:
            time.sleep(0.1)
    process.terminate()
    process.wait(timeout=10)
    raise RuntimeError("路由程序启动超时。")


def set_mode(store, mode):
    if mode not in ("plan-first", "api-only"):
        raise ValueError("不支持的路由模式。")
    files = management(store, "credentials").get("files", [])
    for item in files:
        if item.get("provider") not in (None, "codex"):
            continue
        management(store, "credentials/status",
                   {"name": item["name"], "disabled": mode == "api-only"}, "PATCH")
    settings = store.settings()
    settings["mode"] = mode
    store.save(settings)
