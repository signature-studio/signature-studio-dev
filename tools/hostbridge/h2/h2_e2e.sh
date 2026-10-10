#!/usr/bin/env bash
# h2_e2e.sh — HB-H2 (CAB-91): hostbridge surrogate ハーネスの 1 コマンド検収。
#   bash tools/hostbridge/h2/h2_e2e.sh [--skip-native]
#   1) lowbase (LB_BASE=0x10000) x64c 入口拡張 module のビルド (tools/ott/entry の coverage を再利用)
#   2) native 実機械語参照値の取得 (tools/ott/entry/entry_nat.py に h2_scen.json を食わせ)
#   3) surrogate_harness.mjs: HostBridge 経由で VSTPluginMain 駆動 + round-trip + native 突合
#   4) tools/hostbridge/lowbase/lowbase_e2e.sh (--no-chrome) で既存検収の継続性を確認
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
HB="$(cd -- "$HERE/.." && pwd)"
NODE_BIN="$(command -v node || true)"; [ -n "$NODE_BIN" ] || NODE_BIN="$(ls /opt/emsdk/node/*/bin/node 2>/dev/null | head -1)"
mkdir -p "$HERE/work"

echo "[h2_e2e] [1/4] module build (lowbase LB_BASE=0x10000, 入口拡張 lift)"
bash "$HERE/build_h2_lb.sh" 2>&1 | grep -E "^\[build_h2_lb" | tail -3

echo "[h2_e2e] [2/4] native 参照値 (実機械語, tools/ott/entry/entry_nat.py)"
python3 "$HERE/h2_scen.py" "$HERE/work/scen.json"
python3 -u tools/ott/entry/entry_nat.py --out "$HERE/work/natref.json" --scen "$HERE/work/scen.json" --only h2_full --only getp_range --only op45 --only op47 --only op48 --only op49 --only op35 --only op8 --only chunk_rt --only virt_plabel --only virt_pname 2>&1 | tail -2

echo "[h2_e2e] [3/4] surrogate harness (HostBridge 経由駆動 + native 突合)"
RC=0
"$NODE_BIN" "$HERE/surrogate_harness.mjs" --out "$HERE/work/h2_result.json" || RC=1

echo "[h2_e2e] [4/4] lowbase 既存 e2e の継続性確認"
bash "$HB/lowbase/lowbase_e2e.sh" --no-chrome --quick 2>&1 | tail -2 || { echo "[h2_e2e] lowbase e2e 失敗" >&2; RC=1; }
[ "$RC" = "0" ] && echo "[h2_e2e] PASS" || echo "[h2_e2e] FAIL"
exit $RC
