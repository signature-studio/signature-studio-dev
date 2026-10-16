#!/usr/bin/env bash
# 実インスタンス probe: CreateReverbInstance を native 実行し、返された状態と Process_Fruity の結果を実測する (inst_probe.c)。
# usage: FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/libreverb/inst_probe.sh
# 判定: 本文の期待値 (REPORT §7) と一致すれば exit 0。一致しなければ exit 1 (初期化経路が変わった可能性。REPORT §7 を更新する)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
source "$ROOT/env.sh"
DLL="${REVERB_DLL:-$FL_WIN64_DIR/extracted/block24352_PE.bin}"
[ -f "$DLL" ] || { echo "[inst] Reverb.dll not found: $DLL (FL_WIN64_DIR=$FL_WIN64_DIR)"; exit 2; }
W="$ROOT/work/lift/libreverb/inst"; mkdir -p "$W"
python3 "$HERE/locate.py" "$DLL" "$W/loc" > /dev/null
CR=$(python3 -c "import json;print('%x'%json.load(open('$W/loc/ranges.json'))['create_rva'])")
FR=$(python3 -c "import json;print('%x'%json.load(open('$W/loc/ranges.json'))['fruity']['begin'])")
gcc -O1 -w -o "$W/inst_probe" "$HERE/inst_probe.c"
"$W/inst_probe" "$W/loc/image.bin" "$CR" "$FR" ctor | tee "$W/inst_probe.out"
# 陰性対照 (noctor): CreateReverbInstance を呼ばない空の状態では、観測されるポインタ書き込みは 0 件。
"$W/inst_probe" "$W/loc/image.bin" "$CR" "$FR" noctor | tee "$W/inst_probe_noctor.out"
grep -q 'WRITES_TOTAL=0 WRITES_OBJ=0 WRITES_PTR=0 ' "$W/inst_probe_noctor.out" \
  || { echo "[inst] MISMATCH: noctor でポインタ書き込みが観測された (観測手段が偽陽性)"; exit 1; }
# 陽性対照 (selftest): C 側から 14 本へ書いた値を、書き込みとして 14 件・image 外の RIP で観測できること。
"$W/inst_probe" "$W/loc/image.bin" "$CR" "$FR" selftest | tee "$W/inst_probe_selftest.out"
grep -q '^WRITES_TOTAL=14 WRITES_OBJ=14 WRITES_PTR=14 WRITES_OUTSIDE_IMAGE=14 PTR_SLOTS_SEEN=14$' "$W/inst_probe_selftest.out" \
  || { echo "[inst] MISMATCH: selftest の陽性対照が 14 件観測されない (観測手段が見逃す)"; exit 1; }
# 期待値 (REPORT §7 の実測): ctor は非 NULL・vptr = img+0x603c0・14 本の遅延線ポインタは全て 0・
# 遅延線 2 本 (0x290/0x298) は確保済み (BUF 非 NULL・IDX=0・MASK=0xfff)・Process_Fruity は SIGSEGV (11)
grep -qx 'CREATE_NONNULL=1' "$W/inst_probe.out" \
  && grep -qx 'VPTR_RVA=0x603c0' "$W/inst_probe.out" \
  && grep -qx 'PTR14_ZERO=14' "$W/inst_probe.out" \
  && grep -q '^SUB_290_NONNULL=1 BUF_NONNULL=1 IDX=0 MASK=0xfff$' "$W/inst_probe.out" \
  && grep -q '^SUB_298_NONNULL=1 BUF_NONNULL=1 IDX=0 MASK=0xfff$' "$W/inst_probe.out" \
  && grep -qx 'FRUITY_SIGNAL=11' "$W/inst_probe.out" \
  && grep -qx 'OTHER_WRITES=14 PTRVAL_WRITES=4 REGIONS=5' "$W/inst_probe.out" \
  && { echo "[inst] OK: 実測値は REPORT §7 の期待値と一致 (ctor 状態では Process_Fruity が落ちる)"; exit 0; }
echo "[inst] MISMATCH: REPORT §7 の期待値と違う"; exit 1
