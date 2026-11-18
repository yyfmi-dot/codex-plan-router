"""One-time provider metadata migration; message and turn contents stay intact."""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
import tomlkit

from .storage import lock, read, save


class History:
    def __init__(self, store):
        self.store = store
        self.home = store.codex_home()
        self.ledger_path = store.data / "history-ledger.json"

    def databases(self):
        paths = [self.home / "state_5.sqlite"]
        config = self.home / "config.toml"
        doc = tomlkit.parse(config.read_text() if config.exists() else "")
        extra = doc.get("sqlite_home") or os.environ.get("CODEX_SQLITE_HOME")
        if extra:
            path = Path(str(extra)).expanduser()
            if not path.is_absolute():
                path = self.home / path
            paths.append(path / "state_5.sqlite")
        return list(dict.fromkeys(p.resolve() for p in paths if p.exists()))

    @staticmethod
    @contextmanager
    def connection(path):
        connection = sqlite3.connect(str(path), timeout=3)
        connection.execute("PRAGMA busy_timeout=3000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def scan(self):
        threads, unsupported = {}, set()
        for path in self.databases():
            with self.connection(path) as db:
                columns = {r[1] for r in db.execute("PRAGMA table_info(threads)")}
                if not {"id", "model_provider", "rollout_path"}.issubset(columns):
                    raise RuntimeError("Codex 历史数据库版本不兼容；未修改，请更新插件。")
                for thread_id, rollout in db.execute(
                        "SELECT id,rollout_path FROM threads WHERE model_provider='openai'"):
                    record = threads.setdefault(thread_id, {"files": [], "databases": []})
                    record["databases"].append(str(path))
                    if rollout and Path(rollout).exists() and not str(rollout).endswith(".jsonl"):
                        unsupported.add(thread_id)
        for dirname in ("sessions", "archived_sessions"):
            root = self.home / dirname
            if not root.exists():
                continue
            for path in root.rglob("*.jsonl"):
                if path.is_symlink():
                    continue
                try:
                    with path.open("rb") as stream:
                        line = stream.readline(2 * 1024 * 1024)
                    meta = json.loads(line)
                    payload = meta.get("payload", {})
                    if meta.get("type") != "session_meta" or payload.get("model_provider") != "openai":
                        continue
                    thread_id = str(uuid.UUID(payload["id"]))
                    threads.setdefault(thread_id, {"files": [], "databases": []})["files"].append(str(path))
                except (OSError, ValueError, KeyError):
                    continue
        return threads, unsupported

    def rewrite(self, path, source, target, backup_root):
        path = Path(path)
        if not path.exists() or path.is_symlink():
            return
        with path.open("rb") as stream:
            line = stream.readline(2 * 1024 * 1024)
            meta = json.loads(line)
            if meta.get("type") != "session_meta" or meta.get("payload", {}).get("model_provider") != source:
                return
            backup = backup_root / "files" / (hashlib.sha256(str(path).encode()).hexdigest() + ".jsonl")
            if not backup.exists():
                backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copyfile(path, backup)
                backup.chmod(0o600)
            meta["payload"]["model_provider"] = target
            fd, temp = tempfile.mkstemp(prefix=".provider-migration-", dir=str(path.parent))
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "wb") as output:
                    output.write((json.dumps(meta, ensure_ascii=False, separators=(",", ":")) + "\n").encode())
                    shutil.copyfileobj(stream, output, length=1024 * 1024)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temp, path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)

    @contextmanager
    def native_lease(self, thread_id):
        directory = self.home / "thread-writer-locks"
        with ExitStack() as leases:
            # Coordinate creation/acquisition with native lease-file cleanup.
            # Release the short directory barrier after the per-thread lock is held.
            with lock(directory / ".coordination.lock", blocking=False, shared=True):
                leases.enter_context(lock(directory / (thread_id + ".lock"), blocking=False))
            yield

    def run(self, restore=False):
        with lock(self.store.data / "history-operation.lock"):
            ledger = read(self.ledger_path, {})
            if not ledger:
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
                ledger = {"version": 1, "backup": str(self.store.data / "backups/history" / stamp),
                          "entries": {}}
            backup_root = Path(ledger["backup"])
            backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            if restore:
                threads, unsupported = ledger["entries"], set()
            else:
                threads, unsupported = self.scan()
                # Resume any write interrupted after its durable intent was saved.
                for thread_id, record in ledger["entries"].items():
                    if not record.get("complete"):
                        threads.setdefault(thread_id, record)
            migrated, pending = 0, len(unsupported)
            for thread_id, record in list(threads.items()):
                if thread_id in unsupported:
                    continue
                try:
                    uuid.UUID(thread_id)
                    # Codex's native per-thread writer lease. A live thread is deferred
                    # until its owner releases the lease; never replace an open rollout.
                    with self.native_lease(thread_id):
                        if not restore:
                            previous = ledger["entries"].get(thread_id, {})
                            record = {
                                "files": list(dict.fromkeys(previous.get("files", []) + record["files"])),
                                "databases": list(dict.fromkeys(previous.get("databases", []) + record["databases"])),
                                "complete": False,
                            }
                            ledger["entries"][thread_id] = record
                            save(self.ledger_path, ledger)
                        for database in record.get("databases", []):
                            database_path = Path(database)
                            if not database_path.exists():
                                continue
                            db_backup = backup_root / ("state-" + hashlib.sha256(database.encode()).hexdigest()[:16] + ".sqlite")
                            if not db_backup.exists():
                                with self.connection(database_path) as source:
                                    with self.connection(db_backup) as dest:
                                        source.backup(dest)
                                db_backup.chmod(0o600)
                        source_provider, target = ("custom", "openai") if restore else ("openai", "custom")
                        for file in record.get("files", []):
                            self.rewrite(file, source_provider, target, backup_root)
                        for database in record.get("databases", []):
                            if Path(database).exists():
                                with self.connection(Path(database)) as db:
                                    db.execute("UPDATE threads SET model_provider=? WHERE id=? AND model_provider=?",
                                               (target, thread_id, source_provider))
                        record["complete"] = True
                        record["restored"] = restore
                        migrated += 1
                        save(self.ledger_path, ledger)
                except (BlockingIOError, sqlite3.OperationalError):
                    pending += 1
            result = {"migrated": migrated, "pending": pending, "unsupported_compressed": len(unsupported),
                      "backup": str(backup_root), "restored": restore}
            save(self.store.data / "history-status.json", result)
            return result
