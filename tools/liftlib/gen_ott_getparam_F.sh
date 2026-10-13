#!/usr/bin/env bash
# gen_ott_getparam_F.sh — targets/ott_getparam.json の passes.icall.funcs (F.txt) を生成する (#415)。
# 入力: ${OTT_DLL} (既定 $ANALYSIS_DIR/plugins/ott/binaries/OTT_vst2_win64.dll)。
# 出力: tools/liftlib/work/ott_getparam/F.txt (gitignore 対象の work/ 配下)。
# 依存: python3 + capstone + pefile (tools/icall/closure.py が import する)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../.." && pwd)"
ANALYSIS_DIR="${ANALYSIS_DIR:-/home/ubuntu/work/analysis}"
OTT_DLL="${OTT_DLL:-$ANALYSIS_DIR/plugins/ott/binaries/OTT_vst2_win64.dll}"
W="$HERE/work/ott_getparam"; mkdir -p "$W"
# roots = getParameter (function_18011e5a0) の VA 単体。closure で直接 call/tail-jmp 閉包を取る。
printf '0x18011e5a0\n' > "$W/roots.txt"
python3 "$REPO/tools/icall/closure.py" --pe "$OTT_DLL" --roots "$W/roots.txt" --out "$W/F.txt"
echo "[gen_ott_getparam_F] OK: $W/F.txt"
