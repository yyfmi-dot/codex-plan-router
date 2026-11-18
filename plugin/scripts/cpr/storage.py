from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import fcntl
import json
import os
import tempfile


def atomic(path: Path, data: bytes, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def save(path, value):
    atomic(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


@contextmanager
def lock(path: Path, blocking=True, shared=False):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a+b") as stream:
        os.chmod(path, 0o600)
        fcntl.flock(stream.fileno(), (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) |
                    (0 if blocking else fcntl.LOCK_NB))
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class Store:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get("CODEX_PLAN_ROUTER_HOME") or
                         (Path.home() / ".local/share/codex-plan-router")).expanduser().resolve()
        self.data = self.root / "data"
        self.runtime = self.root / "runtime"
        self.settings_path = self.data / "settings.json"
        self.access_path = self.data / "access.json"
        self.config_path = self.data / "engine.json"
        self.lock_path = self.data / "controller.lock"

    @property
    def auths(self):
        return self.data / ("cc-switch-auths" if self.settings().get("credential_source") == "cc-switch" else "auths")

    def settings(self):
        return read(self.settings_path, {})

    def access(self):
        return read(self.access_path, {})

    def save(self, settings):
        save(self.settings_path, settings)

    def codex_home(self):
        return Path(self.settings()["codex_home"])
