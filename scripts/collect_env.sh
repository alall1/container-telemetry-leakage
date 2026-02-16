#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-results/env}"
mkdir -p "$OUT_DIR"

echo "[*] Capturing environment into $OUT_DIR"

# OS / kernel
uname -a > "$OUT_DIR/kernel.txt"
cat /etc/os-release > "$OUT_DIR/os_release.txt"

# Docker
docker version > "$OUT_DIR/docker_version.txt"
echo -e "\n---\n" >> "$OUT_DIR/docker_version.txt"
docker info >> "$OUT_DIR/docker_version.txt"

# cgroup
{
  echo "stat -fc %T /sys/fs/cgroup:"
  stat -fc %T /sys/fs/cgroup
  echo
  echo "mount | grep cgroup:"
  mount | grep cgroup || true
} > "$OUT_DIR/cgroup.txt"

# CPU / memory
{
  echo "lscpu:"
  lscpu || true
  echo
  echo "free -h:"
  free -h || true
} > "$OUT_DIR/cpu_mem.txt"

# Python env (best-effort; works if venv active)
{
  echo "python3 --version:"
  python3 --version || true
  echo
  echo "pip freeze:"
  python3 -m pip freeze || true
} > "$OUT_DIR/python.txt"

# Git state
{
  echo "git rev-parse HEAD:"
  git rev-parse HEAD || true
  echo
  echo "git status --porcelain:"
  git status --porcelain || true
} > "$OUT_DIR/git.txt"

echo "[*] Done."

