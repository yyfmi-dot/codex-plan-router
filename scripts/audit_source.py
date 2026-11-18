#!/usr/bin/env python3
"""Scan exactly the indexed public source, never local credential stores."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "OpenAI project credential": rb"sk-(?:proj-|svcacct-)[A-Za-z0-9_-]{20,}",
    "GitHub credential": rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})",
    "private key": rb"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----",
    "personal macOS path": rb"/Users/(?!<|example(?:/|\b)|test(?:/|\b)|user(?:/|\b)|runner(?:/|\b))[A-Za-z0-9_.-]+/",
}
FORBIDDEN = {"auth.json", "access.json", "settings.json", "engine.json", "codex_oauth_auth.json", ".DS_Store"}
paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
failures = []
count = 0
for name in filter(None, paths):
    path = Path(name)
    if path.name in FORBIDDEN or any(p in path.parts for p in (".build", "dist", "__pycache__", "node_modules", "target")) or name.startswith("companion/cc-switch/"):
        failures.append((name, "private or generated file"))
        continue
    data = subprocess.check_output(["git", "show", ":" + name], cwd=ROOT)
    count += 1
    for label, pattern in PATTERNS.items():
        if re.search(pattern, data):
            failures.append((name, label))
if not count:
    raise SystemExit("No indexed source to audit; stage the intended release first.")
if failures:
    for name, label in failures:
        print(name + ": " + label, file=sys.stderr)
    raise SystemExit(1)
print("Audited %s indexed source files; no credential or private-path matches." % count)
