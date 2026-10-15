#!/usr/bin/env bash
# py233_getrecppb_probe.sh — PY-233: general.getRecPPB の切替先 (0x15e4558・0x15e35c8・0x16ba7f0・0x16ba808) を
# FLEngine boot (shim 経路・units 209 停止) で観測する。観測点 2 つ (0xd68d90 入口・0x412a0d 停止点) と
# 書込み監視 (FLE_WWATCH) を入れた variant を作って boot する。
#
#   bash tools/flelift/boot/py233_getrecppb_probe.sh      # 前提: 先に fle6_measure.sh で work/boot/lift を作る
#
# 前提: FL_WIN64_DIR (fl-win64 展開先) / SS_EMSDK_ENV (emsdk_env.sh。エントリ ID は docs/REFERENCES.md の [EMSDK]) / node。出力は work/boot/ (gitignore)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
source "$HERE/../../shared/env.sh"
W="${FLE_BOOT_WORK:-$FLE/work/boot}"   # 対照 route (root 無し lift) は別 work を指す
LIFT="$W/lift"
DBG="$W/lift_dbg"
SS_EMSDK_ENV="${SS_EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
[ -f "$LIFT/fle_lifted_s0.c" ] || { echo "[py233] $LIFT が無い。先に bash tools/flelift/boot/fle6_measure.sh を実行する"; exit 2; }

# 観測 C 文: 4 セル (P=0x15e4558, Q=0x15e35c8, 0x16ba7f0, 0x16ba808)・X (getRecPPB の切替結果)・dword [X+0xb20]。
# ポインタは 0x30000000 未満だけ読む (範囲外の読みで wasm を trap させない)。入口は 64 回まで出す。
PROBE='{ static int n_; if (n_++ < 64) { uint64_t p_ = LD64(0x15e4558), q_ = LD64(0x15e35c8); uint64_t c1_ = (p_ && p_ < 0x30000000ULL) ? LD64(p_) : 0, c2_ = (q_ && q_ < 0x30000000ULL) ? LD64(q_) : 0; uint64_t x_ = c1_ ? c1_ : c2_; fprintf(stderr, "[PY233] {tgt} n=%d cell15e4558=%llx cell15e35c8=%llx cell16ba7f0=%llx cell16ba808=%llx c1=%llx c2=%llx X=%llx Xb20=%x\n", n_, (unsigned long long)p_, (unsigned long long)q_, (unsigned long long)LD64(0x16ba7f0), (unsigned long long)LD64(0x16ba808), (unsigned long long)c1_, (unsigned long long)c2_, (unsigned long long)x_, (x_ && x_ < 0x30000000ULL) ? LD32(x_ + 0xb20) : 0xffffffffu); } }'

# fill (f_6a7b70: rcx=dst・edx=val・r8=DWORD 個数) の入口。PY-123 の記録どおり 0 化の源か (REPORT_APPENDIX_PY123.md §2)。
FILL_PROBE='{ static int n_; if (n_++ < 16) fprintf(stderr, "[PY233-fill] n=%d dst=%llx val=%llx cnt=%llx cell15e4558=%llx cell15e35c8=%llx\n", n_, (unsigned long long)R[RCX], (unsigned long long)R[RDX], (unsigned long long)R[R8], (unsigned long long)LD64(0x15e4558), (unsigned long long)LD64(0x15e35c8)); }'

rm -rf "$DBG" && cp -r "$LIFT" "$DBG"
for k in 0 1 2 3 4 5 6 7; do
  # 0xd68d90 は shard 7、0x412a0d (unit 209 停止の call 直前) は shard 2 にある。他 shard では解決されず 0 hit になる。
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0xd68d90,0x412a0d,0xd69310,0x13751d0 --c "$PROBE" || true
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x6a7b70 --c "$FILL_PROBE" || true
done
echo "[py233] probes: $(grep -c 'PY233' "$DBG"/fle_lifted_s*.c | awk -F: '{s+=$2} END {print s}') (expect 5: 0xd68d90・0x412a0d・0xd69310 (getRecPPB 本体)・0x13751d0 (icall 分岐の関数) + fill 入口。root 無し lift では fill が 0)"

# 書込み監視: 4 セルの値が変わる書込みを出す (STX/STY は fle_cpu.h 側で記録されるため、書込み元 VA は出ない)。
FLE_LIFT_DIR="$DBG" FLE_LABEL=wwatch FLE_SHARDS=8 \
  FLE_EXTRA_CCF="-DFLE_WWATCH -DFLE_WWATCH_SLOTS=0x15e4558ull,0x15e35c8ull,0x16ba7f0ull,0x16ba808ull" \
  SS_EMSDK_ENV="$SS_EMSDK_ENV" bash "$HERE/build.sh" plain

LOG="$W/run_py233_probe.log"
FLE_IPP=1 FLE_DIAG_NULLFILL="${FLE_DIAG_NULLFILL:-0}" FLE_BOOT_VARIANT=plain FLE_BOOT_LOG_CAP=268435456 FLE_BOOT_TIME_CAP=300 FLE_BOOT_QUIET_BIN=1 timeout "${FLE_BOOT_TIMEOUT:-600}" node "$HERE/fle_boot.mjs" "$W/fleboot_wwatch.cjs" "$W/py233_probe.json" --boot-only > "$LOG" 2>&1 || true
echo "[py233] PY233 行: $(grep -c '\[PY233\]' "$LOG" || true) (0xd68d90 入口 = 0 件なら未到達)"
grep -E '\[PY233|fle_wwatch\]|FLEBOOT_RESULT' "$LOG" | cut -c1-400
