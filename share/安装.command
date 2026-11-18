#!/bin/zsh
set -e
router_bundle_dir="$(cd "$(dirname "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  print "请先安装 Python 3.9 或更新版本，再运行本安装程序。"
  read "router_install_reply?按回车关闭…"
  exit 1
fi
python3 "$router_bundle_dir/install.py"
read "router_install_reply?按回车关闭安装窗口…"
