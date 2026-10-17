#!/usr/bin/env bash
# py4877_pred_e_probe.sh — PY-4877: 述語 E (0x193fce0 + i*0xc0) の実行時の値と、
# 初期化関数 0x12d0cc0・0x12d1760 の実行の有無を FLEngine boot (既定経路・FLE_IPP 未指定) で観測する。
# 観測点: 述語 0x12d8d30 の入口で E[1..999] の +0x84・+0x10・+0x14・[E+0x20]・[E+0x28] を最初の呼出し時にダンプし、
# 以後の呼出しは回数だけ数える。patternCount 入口 0xd64d40・0x12d0cc0・0x12d1760 は入口で呼出し回数と戻り番地を出す。
# 制御: 同じ bin で 0x12d0cc0 の probe が 1 件発火することを probe 機構の動作確認にする (発火 0 件なら他の 0 件は読めない)。
# 0x6a7b70 は既定経路の lift に入らない (FLE_EXTRA_ROOTS 未指定) ので制御に使えない。
#
#   bash tools/flelift/boot/py4877_pred_e_probe.sh   # 前提: 先に fle6_measure.sh で work/boot/lift を作る
#
# 既定経路 (FLE_IPP 未指定 = fle_boot.mjs の既定 mode 3・units 895 まで進む) で測る。
# 注意: 既定は shim 無効ではなく mode 3 (ILTools 分岐入力・ipp_on=true)。shim 無効は FLE_IPP=0 (ネガコン)。
# shim 経路 (FLE_IPP=1) は units 209 で止まり述語に届かない。
# 前提: FL_WIN64_DIR / SS_EMSDK_ENV / node。出力は work/boot/ (gitignore)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
source "$HERE/../../shared/env.sh"
W="${FLE_BOOT_WORK:-$FLE/work/boot}"
LIFT="$W/lift"
DBG="$W/lift_dbg4877"
SS_EMSDK_ENV="${SS_EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
[ -f "$LIFT/fle_lifted_s0.c" ] || { echo "[py4877] $LIFT が無い。先に bash tools/flelift/boot/fle6_measure.sh を実行する"; exit 2; }

# 述語 0x12d8d30 入口 (patternCount・isPatternDefault・直接呼出しの全経路を拾う): 初回だけ E[1..999] を出す (非 0 の行のみ)。
PC_PROBE='{ static int n_; n_++; fprintf(stderr, "[PY4877-PC] n=%d ecx=%x\n", n_, (unsigned)R[1]); if (n_ == 1) { for (int i_ = 1; i_ <= 999; i_++) { uint64_t e_ = 0x193fce0ULL + (uint64_t)i_ * 0xc0ULL; uint8_t b84_ = LD8(e_ + 0x84), b14_ = LD8(e_ + 0x14); uint32_t d10_ = LD32(e_ + 0x10); uint64_t q20_ = LD64(e_ + 0x20), q28_ = LD64(e_ + 0x28); if (b84_ || b14_ || d10_ || q20_ || q28_) fprintf(stderr, "[PY4877-E] i=%d p84=%02x p10=%08x p14=%02x p20=%llx p28=%llx\n", i_, b84_, d10_, b14_, (unsigned long long)q20_, (unsigned long long)q28_); } } }'

# 0x12d0cc0・0x12d1760 入口: 呼出し回数と戻り番地 (スタック top) を出す。最初の 32 回まで。
mk_fn_probe() { echo '{ static int n_; if (n_++ < 32) fprintf(stderr, "[PY4877-'"$1"'] n=%d ret=%llx ecx=%x\n", n_, (unsigned long long)LD64(R[4]), (unsigned)R[1]); }'; }

# 0x12de002 = 0x12d0cc0 の呼出し直後 (既定経路で観測された唯一の呼出し・呼出元 0x12ddffd)。呼出し後の E[0..999] の非 0 行を数える。
AFTER_PROBE='{ static int a_; if (a_++ < 1) { int nz_ = 0; for (int i_ = 0; i_ <= 999; i_++) { uint64_t e_ = 0x193fce0ULL + (uint64_t)i_ * 0xc0ULL; uint8_t b84_ = LD8(e_ + 0x84), b14_ = LD8(e_ + 0x14); uint32_t d10_ = LD32(e_ + 0x10); uint64_t q20_ = LD64(e_ + 0x20), q28_ = LD64(e_ + 0x28); if (b84_ || b14_ || d10_ || q20_ || q28_) { nz_++; if (nz_ <= 40) fprintf(stderr, "[PY4877-AFTER] i=%d p84=%02x p10=%08x p14=%02x p20=%llx p28=%llx\n", i_, b84_, d10_, b14_, (unsigned long long)q20_, (unsigned long long)q28_); } } fprintf(stderr, "[PY4877-AFTER-N] nonzero_rows=%d\n", nz_); } }'

rm -rf "$DBG" && cp -r "$LIFT" "$DBG"
for k in 0 1 2 3 4 5 6 7; do
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x12de002 --c "$AFTER_PROBE" || true
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c"  --at 0x12d8d30 --c "$PC_PROBE" || true
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x12d0cc0 --c "$(mk_fn_probe 0cc0)" || true
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x12d1760 --c "$(mk_fn_probe 1760)" || true
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0xd64d40 --c "$(mk_fn_probe d64d40)" || true
done
echo "[py4877] probe 挿入行数: $(grep -c 'PY4877' "$DBG"/fle_lifted_s*.c | awk -F: '{s+=$2} END {print s}') (AFTER・述語・0x12d0cc0・0x12d1760・0xd64d40 の各 1 行。lift に無い点は挿入されない)"

FLE_LIFT_DIR="$DBG" FLE_LABEL=e4877 FLE_SHARDS=8 SS_EMSDK_ENV="$SS_EMSDK_ENV" bash "$HERE/build.sh" plain

LOG="$W/run_py4877_probe.log"
FLE_PY4877_PC=1 FLE_DIAG_NULLFILL=0 FLE_BOOT_VARIANT=plain FLE_BOOT_LOG_CAP=268435456 FLE_BOOT_TIME_CAP=300 FLE_BOOT_QUIET_BIN=1 timeout "${FLE_BOOT_TIMEOUT:-600}" node "$HERE/fle_boot.mjs" "$W/fleboot_e4877.cjs" "$W/py4877_probe.json" --boot-only > "$LOG" 2>&1 || true
echo "[py4877] PY4877-PC 行: $(grep -c '\[PY4877-PC\]' "$LOG" || true)"
grep -E '\[PY4877|FLEBOOT_RESULT|FLEBOOT_PY4877' "$LOG" | cut -c1-300 | head -400
