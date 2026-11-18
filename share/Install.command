#!/bin/zsh
set -e
router_bundle_dir="$(cd "$(dirname "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  print "Install Python 3.9 or later before running this installer."
  read "router_install_reply?Press Return to close…"
  exit 1
fi
python3 "$router_bundle_dir/install.py"
read "router_install_reply?Press Return to close the installer…"
