#!/usr/bin/env bash
# M5 native_fx (実機 x86 参照) ビルド — tools/m3 の実績 (m3_perf_native.c) を踏襲
set -euo pipefail
cd "$(dirname "$0")"
cc -O2 -o work/native_fx native_fx.c
echo "[native_fx] built work/native_fx"
