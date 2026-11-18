from pathlib import Path
import re
import shutil
import subprocess

MINIMUM_CLI = (0, 167, 0)


def native_cli(explicit=None):
    paths = [Path(explicit)] if explicit else []
    if not explicit:
        found = shutil.which("codex")
        if found:
            paths.append(Path(found))
        paths += [
            Path("/Applications/Codex.app/Contents/Resources/codex"),
            Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"),
        ]
        paths += list((Path.home() / ".vscode/extensions").glob("openai.chatgpt-*/bin/macos-*/codex"))
    found = []
    for path in dict.fromkeys(paths):
        if not path.is_file():
            continue
        try:
            result = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=8)
            version = re.search(r"(\d+)\.(\d+)\.(\d+)", result.stdout)
            if result.returncode == 0 and version:
                found.append((tuple(map(int, version.groups())), path))
        except Exception:
            continue
    if not found or max(v for v, _ in found) < MINIMUM_CLI:
        raise RuntimeError("请先安装或更新 Codex 桌面客户端（需要 Codex CLI 0.167+）。")
    return max(found, key=lambda row: row[0])[1]
