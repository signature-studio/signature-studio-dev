#!/usr/bin/env bash
# fw_269_verify.sh — CAB-269 受入条件 1/2/3 の 1 コマンド再現 (stage-1 成果物のみの空 W → e2e)。
#
#   bash fw_269_verify.sh [SRC_STAGE1_DIR]
#     SRC_STAGE1_DIR: stage-1 成果物 (fw_icall.dll / fw_map.json / fw[0-7].restored.ll /
#                     r2.restored.ll / r3.restored.ll) を持つ dir。既定は共有 tools/plugins/work/fw。
#
# 手順 (規則 45 = クリーン HEAD 検証):
#   ① `git archive HEAD -- tools/plugins/framework` を work/verify_269/snap に展開 (未コミット WIP を含まない)
#   ② 独立 W (work/verify_269/fw) に SRC の stage-1 成果物をハードリンク (共有 work/fw は書換えない)
#   ③ FW_W=その W で snapshot の fw_stage2.sh を実行 (steps 1-18 全部 = stage-2 を最初から再構築)
#   ④ smoke ×3 + fw_smoke_check.py で同値検証 (dispatch=38 units_done=0 va=1 heap=1 ff=0)
# 出力: work/verify_269/run.log / smoke{1,2,3}.log
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
T=/home/ubuntu/work/webstudio
SRC="${1:-$T/tools/plugins/work/fw}"
V="$HERE/work/verify_269"
SNAP="$V/snap"
W="$V/fw"
STAGE1="fw_icall.dll fw_map.json fw0.restored.ll fw1.restored.ll fw2.restored.ll fw3.restored.ll \
fw4.restored.ll fw5.restored.ll fw6.restored.ll fw7.restored.ll r2.restored.ll r3.restored.ll"

mkdir -p "$W" "$V/tmp"
cd "$HERE"

# ---- 1. stage-1 成果物を独立 W にハードリンク (読取のみ。W 側が書換えても SRC には影響しない) ----
miss=0
for f in $STAGE1; do
  [ -f "$SRC/$f" ] || { echo "[v269] stage-1 欠落: $SRC/$f" >&2; miss=1; continue; }
  ln -f "$SRC/$f" "$W/$f"
done
[ $miss = 0 ] || exit 1

# ---- 2. clean HEAD スナップショット ----
rm -rf "$SNAP"; mkdir -p "$SNAP"
git -C "$T" archive HEAD -- tools/plugins/framework | tar -x -C "$SNAP"
FW="$SNAP/tools/plugins/framework"
[ -f "$FW/fw_stage2.sh" ] || { echo "[v269] snapshot 失敗" >&2; exit 1; }
echo "[v269] snapshot commit: $(git -C "$T" rev-parse --short HEAD)"

# ---- 3. stage-2 e2e (stage-1 のみの空 W から) ----
export TMPDIR="$V/tmp"
start=$(date +%s); load0=$(cut -d' ' -f1-3 /proc/loadavg)
FW_W="$W" bash "$FW/fw_stage2.sh" > "$V/run.log" 2>&1 && rc=0 || rc=$?
load1=$(cut -d' ' -f1-3 /proc/loadavg); end=$(date +%s)
echo "[v269] fw_stage2.sh exit=$rc  実測 $((end-start)) s  load avg $load0 -> $load1"
[ $rc = 0 ] || { tail -30 "$V/run.log"; exit 1; }

# ---- 4. smoke ×3 (同値検証) ----
export PATH="$PATH:/opt/emsdk/node/24.19.0_64bit/bin"
for i in 1 2 3; do
  t0=$(date +%s%N)
  node "$FW/fw_run.mjs" "$W/fw_image.bin" "$W/fw_route.cjs" > "$V/smoke$i.log" 2>&1 || { echo "[v269] smoke$i FAIL"; cat "$V/smoke$i.log"; exit 1; }
  t1=$(date +%s%N)
  echo "[v269] smoke$i: $(( (t1-t0)/1000000 )) ms  $(grep -o 'dispatch=[0-9]* units_done=[0-9]* va=[0-9]* heap=[0-9]* ff=[0-9]*' "$V/smoke$i.log")"
done
python3 "$HERE/fw_smoke_check.py" --log "$V/smoke1.log" --wasm "$W/fw_route.wasm"
python3 "$HERE/fw_smoke_check.py" --log "$V/smoke2.log" --wasm "$W/fw_route.wasm"
python3 "$HERE/fw_smoke_check.py" --log "$V/smoke3.log" --wasm "$W/fw_route.wasm"
echo "[v269] ALL PASS (log: $V/run.log / smoke1-3.log)"
