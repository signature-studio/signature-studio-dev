#!/usr/bin/env bash
# outmem_variants.sh — PERF-P22 (#3330): boot 停止時点の出力メモリ (wasm 線形メモリ) の sha256 を変種間で比べる。
#   FL_WIN64_DIR=<fl-win64 展開先> SS_EMSDK_ENV=<emsdk_env.sh> FLE_BOOT_WORK=<repo 外の作業 dir> \
#     bash tools/flelift/boot/outmem_variants.sh build    # gen → lift (無ければ) → plain(-O0) → o2 ∥ o2lto
#     bash tools/flelift/boot/outmem_variants.sh boot     # 3 変種 boot (FLE_BOOT_N 回) + ネガコン (FLE_IPP=0) → outmem_compare.py
#     bash tools/flelift/boot/outmem_variants.sh mutant   # 比較器の検出力: dump の複製 1 本の .data 先頭 1 byte を変えて FAIL (rc 1) になることを見る (boot の後)
# 工程と条件は tools/flelift/boot/fle6_measure.sh (plain = -O0, FLE_SHARDS=8) と variant_boot.sh (FLE_IPP=1) に揃える。
# 生成物はすべて FLE_BOOT_WORK 下 (repo 外。tools/**/work/ は作業場にしない)。結果 JSON は $W/variant/。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
source "$HERE/../../shared/env.sh"
W="${FLE_BOOT_WORK:?FLE_BOOT_WORK (repo 外の作業 dir) を指定する}"
PE="${FLE_PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
SS_EMSDK_ENV="${SS_EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
export FLE_EXTRA_ROOTS="${FLE_EXTRA_ROOTS-0x6a7b70}"   # fle6_measure.sh と同じ (shim 経路の root)
export FLE_SHARDS="${FLE_SHARDS:-8}"
export TMPDIR="$W/tmp"
mkdir -p "$W/tmp" "$W/obj" "$W/variant"
set +u; source "$SS_EMSDK_ENV" > /dev/null 2>&1; set -u
LIFT="$W/lift"
NODE="$(command -v node)"
stage() { echo "[outmem] $1 start $(date -u +%H:%M:%S) load=$(cut -d' ' -f1-3 /proc/loadavg)"; }

do_build() {
  if [ ! -f "$LIFT/lift_meta.json" ]; then
    stage "gen-A + lift"; T=$(date +%s)
    python3 "$HERE/gen_boot.py" --pe "$PE" --out "$W" > /dev/null
    python3 "$HERE/rss_cap.py" --cap-mb 13800 --log "$W/rss_lift.log" -- \
      python3 "$FLE/x64c.py" --pe "$PE" --entries "$W/fle_entries_boot.json" --out "$LIFT" --closure "${FLE_LIFT_CLOSURE:-2}" \
      --img 0x400000 --shift 0 --img-size 0x18c0000 --impbase 0x1D80000 \
      --override 0x4126f0=fle_ov_longjmp --override 0x409410=fle_ov_getmem \
      --override 0x409440=fle_ov_freemem --override 0x4120c0=fle_ov_initunits --shards "$FLE_SHARDS" | tail -3
    python3 "$FLE/fle_data_gen.py" "$PE" "$LIFT/fle_data.c" "$LIFT/lift_meta.json" > /dev/null
    python3 "$HERE/gen_boot.py" --pe "$PE" --meta "$LIFT/lift_meta.json" --out "$W" > /dev/null
    echo "[outmem] lift done in $(( $(date +%s) - T ))s"
  fi
  stage "build plain (-O0)"; T=$(date +%s)
  FLE_CC_JOBS=3 bash "$HERE/build.sh" plain
  echo "[outmem] plain done in $(( $(date +%s) - T ))s"
  # shimx obj (-O1, 共有) は plain で作られる。以下 2 本は並列に走らせても共有物に触れない。
  stage "build o2 ∥ o2lto"; T=$(date +%s)
  FLE_CC_OPT="-O2" FLE_LABEL=o2 FLE_CC_JOBS=2 FLE_CC_RSS_CAP_MB=6000 bash "$HERE/build.sh" plain &
  P1=$!
  python3 "$HERE/rss_cap.py" --cap-mb 12000 --log "$W/rss_lto_total.log" -- \
    env FLE_CC_OPT="-O2 -flto" FLE_LABEL=o2lto FLE_CC_JOBS=2 FLE_CC_RSS_CAP_MB=6000 bash "$HERE/build.sh" plain &
  P2=$!
  R1=0; R2=0; wait "$P1" || R1=$?; wait "$P2" || R2=$?
  echo "[outmem] o2 rc=$R1 / o2lto rc=$R2 in $(( $(date +%s) - T ))s"
  [ "$R1" = 0 ] && [ "$R2" = 0 ]
}

do_boot() {
  N="${FLE_BOOT_N:-2}"
  rm -f "$W/variant/summary.tsv"
  export FLE_OUTMEM_DUMP="$W/outmem"
  FLE_BOOT_WORK="$W" FLE_BOOT_N="$N" bash "$HERE/variant_boot.sh" plain o2 o2lto
  # ネガコン: shim 無し (FLE_IPP=0)。出力を変える入力 (計数・ipp 状態が変わる)。
  FLE_IPP=0 FLE_BOOT_VARIANT=plain "$NODE" "$HERE/fle_boot.mjs" "$W/fleboot_plain.cjs" "$W/variant/boot_plain_negctl.json" --boot-only \
    > "$W/variant/run_plain_negctl.log" 2>&1 || echo "[outmem] negctl rc=$? (IPP 判定 NG 以外なら失敗)"
  python3 "$HERE/outmem_compare.py" "$W/variant" --labels plain o2 o2lto --negctl plain_negctl --dump "$W/outmem"
}

do_mutant() {
  # 比較器の検出力 (WORKFLOW §5): 複製の dump の .data 先頭 (linear 0x13a5000 = 0x400000 + .data RVA 0xfa5000) の 1 byte を反転し、
  # image_writable の不一致で FAIL (rc 1) になることを見る。他の dump はリンクのまま (元データは変えない)。
  M="$W/mutant"; rm -rf "$M"; mkdir -p "$M"
  for f in "$W/outmem"/*.bin; do ln -s "$f" "$M/"; done
  rm "$M/outmem_boot_plain_r1.bin"
  python3 - "$W/outmem/outmem_boot_plain_r1.bin" "$M/outmem_boot_plain_r1.bin" 0x13a5000 <<'PY'
import hashlib, sys
src, dst, off = sys.argv[1], sys.argv[2], int(sys.argv[3], 16)
d = bytearray(open(src, "rb").read())
b0 = d[off]; before = hashlib.sha256(d).hexdigest()[:16]
d[off] ^= 0xFF
after = hashlib.sha256(d).hexdigest()[:16]
open(dst, "wb").write(d)
print(f"mutant: offset 0x{off:x} byte 0x{b0:02x}->0x{d[off]:02x} / dump sha256 {before} -> {after}")
PY
  R=0; python3 "$HERE/outmem_compare.py" "$W/variant" --labels plain o2 o2lto --negctl plain_negctl --dump "$M" || R=$?
  echo "[outmem] mutant compare rc=$R (期待 1)"
  [ "$R" = 1 ]
}

case "${1:-}" in
  build)  do_build ;;
  boot)   do_boot ;;
  mutant) do_mutant ;;
  *) echo "usage: outmem_variants.sh build|boot|mutant"; exit 2 ;;
esac
