"""Package the already-built, feature-enabled Tauri companion for colleagues."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

BASE = Path(__file__).resolve().parent
SOURCE = BASE / "companion/cc-switch"
DIST = BASE / "dist"
DIST.mkdir(exist_ok=True)
version = json.loads((BASE / "plugin/plugin.json").read_text())["version"]
app = SOURCE / "src-tauri/target/release/bundle/macos/CC Switch Plan Router.app"
executable = app / "Contents/MacOS/cc-switch"
assert executable.is_file(), "Build the companion with the plan-router-bridge feature first."
build = hashlib.sha256(executable.read_bytes()).hexdigest()
marker = {"bridge_schema": 1, "version": version, "build": build, "cc_switch_version": "4.0.34"}
resources = app / "Contents/Resources"
resources.mkdir(exist_ok=True)
(resources / "plan-router-companion.json").write_text(json.dumps(marker, indent=2) + "\n")
shutil.copy2(SOURCE / "LICENSE", resources / "CC-Switch-LICENSE")
subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True, capture_output=True)
subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True, capture_output=True)
filename = "CC-Switch-Plan-Router-4.0.34-cpr" + version + "-arm64.zip"
archive = DIST / filename
subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(archive)], check=True)
metadata = dict(marker, file=filename, architecture="arm64", bundle_id="com.ccswitch.desktop",
                sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), signature="ad-hoc", notarized=False)
(DIST / "companion.json").write_text(json.dumps(metadata, indent=2) + "\n")
print(json.dumps({"companion": metadata}))
