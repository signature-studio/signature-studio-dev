#!/usr/bin/env bash
# CAB-101 (ST-T1) の 1 コマンド検収: ビルド → C 単体 → TS 単体 → SIGKILL 跨ぎ e2e → trace 監査。
#   bash tools/startup/glue/glue.sh            (exit 0 = 全 PASS)
#   KEEP=1 で work/ を残す / NOREBUILD=1 でビルドを省略
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
set +u; . /opt/emsdk/emsdk_env.sh >/dev/null 2>&1 || true; set -u
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
[ "${KEEP:-0}" = 1 ] && echo "[glue] KEEP=1: work/ はそのまま"
exec node host/glue_e2e.ts
