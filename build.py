from pathlib import Path
import hashlib
import json
import re
import shutil
import zipfile

BASE = Path(__file__).resolve().parent
PLUGIN = BASE / "plugin"
manifest = json.loads((PLUGIN / "plugin.json").read_text())
version = manifest["version"]
dist = BASE / "dist"
dist.mkdir(exist_ok=True)


def files(root):
    return [p for p in sorted(root.rglob("*")) if p.is_file()
            and "__pycache__" not in p.parts and p.suffix != ".pyc" and p.name != ".DS_Store"]


def checked(path):
    assert not path.is_symlink(), path
    data = path.read_bytes()
    assert not re.search(rb"sk-(?:proj-|svcacct-)[A-Za-z0-9_-]{20,}", data), path
    assert not re.search(rb"/Users/[A-Za-z0-9_.-]+/", data), path
    return data


plugin_zip = dist / ("codex-plan-router-macos-" + version + ".zip")
with zipfile.ZipFile(plugin_zip, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in files(PLUGIN):
        archive.writestr("codex-plan-router/" + str(path.relative_to(PLUGIN)), checked(path))

bundle = dist / ("Codex-Plan-Router-macOS-" + version)
if bundle.exists():
    shutil.rmtree(bundle)
bundle.mkdir()
target = bundle / "plugins/codex-plan-router"
shutil.copytree(PLUGIN, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
for path in (BASE / "share").iterdir():
    if path.is_file() and path.name != ".DS_Store":
        shutil.copy2(path, bundle / path.name)
companion = json.loads((dist / "companion.json").read_text())
assert companion["version"] == version
companion_archive = dist / companion["file"]
assert hashlib.sha256(companion_archive.read_bytes()).hexdigest() == companion["sha256"]
shutil.copy2(companion_archive, bundle / companion_archive.name)
shutil.copy2(dist / "companion.json", bundle / "companion.json")
for name in ("安装.command", "Install.command"):
    (bundle / name).chmod(0o755)
share_zip = dist / ("Codex-Plan-Router-macOS-" + version + "-share.zip")
with zipfile.ZipFile(share_zip, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in files(bundle):
        checked(path)
        archive.write(path, str(path.relative_to(bundle.parent)))

report = {"name": manifest["name"], "version": version, "artifacts": []}
for path in (plugin_zip, share_zip):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        assert not any("__pycache__" in n or n.endswith(".pyc") for n in archive.namelist())
        for item in archive.infolist():
            data = archive.read(item)
            if not item.filename.endswith(".zip"):
                assert not re.search(rb"/Users/[A-Za-z0-9_.-]+/", data)
            if item.filename.endswith(("/安装.command", "/Install.command")):
                assert (item.external_attr >> 16) & 0o111
    report["artifacts"].append({"file": path.name, "bytes": path.stat().st_size,
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
report["credential_and_path_scan_passed"] = True
(dist / "package-verification.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
