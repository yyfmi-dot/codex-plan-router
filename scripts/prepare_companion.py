#!/usr/bin/env python3
"""Fetch a verified upstream archive and apply this project's small companion patch."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def prepare(destination):
    metadata = json.loads((ROOT / "companion/UPSTREAM.json").read_text())
    if destination.exists():
        raise RuntimeError("Destination exists; use a new --destination to preserve local edits.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cpr-upstream-", dir=destination.parent) as temporary:
        stage = Path(temporary)
        archive = stage / "upstream.tar.gz"
        with urllib.request.urlopen(metadata["archive_url"], timeout=90) as response, archive.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != metadata["archive_sha256"]:
            raise RuntimeError("Upstream archive SHA-256 mismatch; nothing was executed.")
        with tarfile.open(archive) as source:
            for item in source.getmembers():
                path = (stage / item.name).resolve()
                if not path.is_relative_to(stage.resolve()) or item.issym() or item.islnk():
                    raise RuntimeError("Unsafe upstream archive entry.")
            source.extractall(stage)
        tree = next(p for p in stage.iterdir() if p.is_dir())
        patch = ROOT / "companion/patches/plan-router-bridge.patch"
        subprocess.run(["git", "apply", "--check", str(patch)], cwd=tree, check=True)
        subprocess.run(["git", "apply", str(patch)], cwd=tree, check=True)
        tree.rename(destination)
    print(json.dumps({"prepared": str(destination), "upstream": metadata["version"], "commit": metadata["commit"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=ROOT / "companion/cc-switch")
    args = parser.parse_args()
    prepare(args.destination.expanduser().resolve())
