#!/usr/bin/env bash
# PSOLA (block24360_PE.bin) の DSP 本体 slot 1–3 を、host 初期化 (鍵 [0x3f7ad0] を設定する 0x1b7d80) の後に
# 元の機械語 (native) だけで呼ぶ。落ちる slot・落ちる RIP を標準出力に出す (#4302 / T-SH-114)。
# 結果の正本は REPORT_APPENDIX_4302.md。
# usage: FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/ildsp/psola_init_probe.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$HERE/../.."
source "$ROOT/env.sh"
DLL="${ILDSP_DLL:-$FL_WIN64_DIR/extracted/block24360_PE.bin}"
[ -f "$DLL" ] || { echo "[psola-init-probe] DLL not found: $DLL"; exit 2; }
W="$ROOT/work/lift/ildsp-psola-init"; rm -rf "$W"; mkdir -p "$W"
WC_ENTRY_RVA=0x1ab540 WC_VTABLE_RVA=0x3e0030 WC_WORK=ildsp-psola \
WC_ROOTS="0x1ab540 0x1ab590 0x1ab6b0 0x1ab800" WC_CALL_SLOTS=6 \
  python3 "$HERE/wc_image.py" "$DLL" "$W" >/dev/null
gcc -O1 -w -I "$W" -o "$W/psola_init_native" "$HERE/psola_init_native.c"
S="$W/psola_init_native"; IMG="$W/image_native.bin"
INIT=0x1b7d80
IN=0x30508000; OUT=0x3050C000
run() { local label="$1"; shift; printf '%-40s ' "$label"; set +e; timeout 20 "$S" "$IMG" "$@" 2>&1 | tr '\n' ' '; printf 'rc=%s\n' "${PIPESTATUS[0]}"; set -e; }
echo "# init=$INIT の後に slot を 1 回ずつ呼ぶ。args: INIT K RDX R8 R9 STACK5 (16 進)。slot 別の引数は REPORT_APPENDIX_4302.md §4"
run "no-init slot1 (r8=out)"        0 1 $IN $OUT 16 0
run "no-init slot3 (r8=n r9=in)"    0 3 0 16 $IN $OUT
run "init slot0"                    $INIT 0 $IN $OUT 16 0
run "init slot1 (r8=out)"           $INIT 1 $IN $OUT 16 0
run "init slot2"                    $INIT 2 $IN $OUT 16 0
run "init slot3 (r8=n r9=in)"       $INIT 3 0 16 $IN $OUT
run "init slot4"                    $INIT 4 $IN $OUT 16 0
run "init slot5"                    $INIT 5 $IN $OUT 16 0
run "init slot3 n=0"                $INIT 3 0 0 $IN $OUT
run "init slot3 rdx=0 r8=0"         $INIT 3 0 0 16 $OUT
