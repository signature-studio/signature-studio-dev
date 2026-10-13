#!/usr/bin/env bash
# gen_ott_getparam_F.sh — targets/ott_getparam.json の passes.icall.funcs (F.txt) を生成する (#415)。
# 入力: ${OTT_DLL} (環境変数必須。OTT_vst2_win64.dll の実パス。docs/REFERENCES.md §4 の PLUGINS_DIR 配下を指す)。
# 出力: tools/liftlib/work/ott_getparam/F.txt (gitignore 対象の work/ 配下)。
# 依存: python3 + capstone + pefile (tools/icall/closure.py が import する)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../.." && pwd)"
: "${OTT_DLL:?OTT_DLL を環境変数で指定してください (例: OTT_DLL=\$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll)}"
W="$HERE/work/ott_getparam"; mkdir -p "$W"
# roots = getParameter (function_18011e5a0) の VA 単体。closure で直接 call/tail-jmp 閉包を取る。
printf '0x18011e5a0\n' > "$W/roots.txt"
python3 "$REPO/tools/icall/closure.py" --pe "$OTT_DLL" --roots "$W/roots.txt" --out "$W/F.txt"
echo "[gen_ott_getparam_F] OK: $W/F.txt"
