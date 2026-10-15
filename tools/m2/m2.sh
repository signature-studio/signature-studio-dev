#!/usr/bin/env bash
# M2 ドライバ: mac x86_64 slice 抽出 + 静的解析成果物の機械化 + Delphi 品質確認
# (strategy.md §4 M2 / §5.7)。
#
#   bash tools/m2/m2.sh
#
# 構成:
#   1. FLEEngine universal2 → x86_64 slice 抽出 (extract_slice.sh)
#   2. win64 FLEEngine_x64.dll の静的基盤 (pescan.py: .pdata/.unwind/IAT)
#   3. Delphi観点候補抽出 (delphi_scan.py: win / delphi_mac_scan.py: mac)
#   4. shim inventory 生成 (shim_inventory.py)
#   5. delphi inventory 生成 (delphi_inventory.py)
#   6. 300KB級副モジュール (EasyFLAC) の IR→wasm PoC (poc_crc8_wasm.sh)
#   7. 関数境界合意検証 (function_boundary.py) — Ghidra headless / RetDec で
#      あらかじめ生成した重い成果物 (work/ 内の json/csv/ll) が存在すれば
#      それを使い、無ければ warning だけ出して継続する (重い解析は 1 回だけ
#      手動で回す運用: README.md を参照)。
#
# 成果物: tools/m2/work/ (gitignored) + 各 md / json。失敗は stderr + exit != 0。

set -euo pipefail

HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
WORK="$HERE/work"
source "$HERE/../shared/env.sh"
DL_FALLBACK="$FL_WIN64_DIR/extracted/block00031_PE.bin"
SLICE="$WORK/FLEngine_x86_64.dylib"

log() { echo "[M2] $*"; }
warn() { echo "[M2] WARN: $*" >&2; }

# -----------------------------------------------------------------
# 0) 前提 / 入力
# -----------------------------------------------------------------
if [ ! -f "$DL_FALLBACK" ]; then
  echo "[M2] FAIL: win64 抽出物の FLEngine が見つかりません: $DL_FALLBACK" >&2
  exit 1
fi

mkdir -p "$WORK"

# -----------------------------------------------------------------
# 1) mac FLEngine slice 抽出 (universal2 → x86_64)
# -----------------------------------------------------------------
if [ ! -f "$SLICE" ]; then
  bash "$HERE/extract_slice.sh"
else
  log "slice は既存のため再利用: $SLICE"
fi

# -----------------------------------------------------------------
# 2) win64 DLL の静的基盤 (.pdata / unwind 情報 / IAT / exports)
# -----------------------------------------------------------------
cp -n "$DL_FALLBACK" "$WORK/" 2>/dev/null || true
WIN_DLL="$WORK/block00031_PE.bin"
if [ ! -f "$WORK/pe_scan_dll.json" ]; then
  python3 "$HERE/pescan.py" --input "$WIN_DLL" --out "$WORK/pe_scan_dll.json"
else
  log "pe_scan_dll.json は既存のため再利用"
fi

# -----------------------------------------------------------------
# 3) Delphi観点候補抽出 (win + mac)
# -----------------------------------------------------------------
if [ ! -f "$WORK/delphi_candidates.json" ]; then
  python3 "$HERE/delphi_scan.py" --input "$WIN_DLL" \
    --scan-json "$WORK/pe_scan_dll.json" \
    --out "$WORK/delphi_candidates.json"
else
  log "delphi_candidates.json は既存のため再利用"
fi

if [ ! -f "$WORK/delphi_mac.json" ]; then
  python3 "$HERE/delphi_mac_scan.py" --input "$SLICE" \
    --out "$WORK/delphi_mac.json"
else
  log "delphi_mac.json は既存のため再利用"
fi

# -----------------------------------------------------------------
# 4) shim inventory (libwinbridge / mac slice / win DLL の import/export)
# -----------------------------------------------------------------
WINBRIDGE="$FL_MAC_DIR/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL/Shared/libwinbridge_x64.dylib"
[ -f "$WORK/libwinbridge_x64.dylib" ] || cp "$WINBRIDGE" "$WORK/libwinbridge_x64.dylib"

python3 "$HERE/shim_inventory.py" \
  --win-dll "$WIN_DLL" --win-scan-json "$WORK/pe_scan_dll.json" \
  --mac-dylib "$SLICE" --winbridge-dylib "$WORK/libwinbridge_x64.dylib" \
  --out-md "$HERE/SHIM_INVENTORY.md" --out-json "$WORK/shim_inventory.json"

# -----------------------------------------------------------------
# 5) delphi inventory (VMT/RTTI class 表 + dbk 除外リスト)
# -----------------------------------------------------------------
python3 "$HERE/delphi_inventory.py" \
  --win-candidates "$WORK/delphi_candidates.json" \
  --mac-scan "$WORK/delphi_mac.json" \
  --winbridge-json "$WORK/shim_inventory.json" \
  --out-md "$HERE/delphi_inventory.md" --out-json "$WORK/delphi_inventory.json"

# -----------------------------------------------------------------
# 6) 300KB級副モジュール IR→wasm PoC (EasyFLAC / _FLAC__crc8)
# -----------------------------------------------------------------
if [ ! -f "$WORK/poc_crc8_results.json" ]; then
  bash "$HERE/poc_crc8_wasm.sh"
else
  log "poc_crc8_results.json は既存のため再利用"
fi

# -----------------------------------------------------------------
# 7) 関数境界合意検証 (重い解析物が揃っていれば実行)
# -----------------------------------------------------------------
GHIDRA_DLL_CSV="$WORK/ghidra_dll/functions_dll.csv"
GHIDRA_SLICE_CSV="$WORK/ghidra_slice/functions_slice.csv"
RETDEC_WIN_DSM="$WORK/engine_win.drc.dsm"
RETDEC_MAC_DSM="$WORK/macbound.drc.dsm"
GROUND_MAC="$WORK/function_starts_mac.txt"

# mac slice の ground truth (LC_FUNCTION_STARTS)
llvm-objdump --macho --function-starts "$SLICE" 2>/dev/null | grep '^0' > "$GROUND_MAC" \
  || warn "mac slice の function starts 取得に失敗"

if [ -f "$GHIDRA_DLL_CSV" ] && [ -f "$RETDEC_WIN_DSM" ]; then
  python3 "$HERE/function_boundary.py" --label win_dll \
    --ghidra-csv "$GHIDRA_DLL_CSV" \
    --retdec-dsm "$RETDEC_WIN_DSM" --dsm-shift -0x400000 \
    --ground "$WORK/pe_scan_dll.json" --ground-kind win \
    --va-base 0x400000 \
    --out-json "$WORK/boundary_win.json" \
    || warn "win boundary 計算に失敗"
elif [ -f "$GHIDRA_DLL_CSV" ]; then
  warn "RetDec win64 dsm がありません (engine_win.drc.dsm)"
  warn "README.md の RetDec 重い解析コマンドで 1 回実行してください"
else
  warn "Ghidra headless 成果物がありません (ghidra_dll/functions_dll.csv)"
  warn "README.md の Ghidra/RetDec 重い解析コマンドで 1 回実行してください"
fi

if [ -f "$GHIDRA_SLICE_CSV" ] && [ -s "$GROUND_MAC" ] && [ -f "$RETDEC_MAC_DSM" ]; then
  python3 "$HERE/function_boundary.py" --label mac_slice \
    --ghidra-csv "$GHIDRA_SLICE_CSV" \
    --retdec-dsm "$RETDEC_MAC_DSM" --dsm-shift 0 \
    --ground "$GROUND_MAC" --ground-kind mac \
    --va-base 0 \
    --out-json "$WORK/boundary_mac.json" \
    || warn "mac boundary 計算に失敗"
elif [ -f "$GHIDRA_SLICE_CSV" ] && [ -s "$GROUND_MAC" ]; then
  python3 "$HERE/function_boundary.py" --label mac_slice_ghidra_only \
    --ghidra-csv "$GHIDRA_SLICE_CSV" \
    --ground "$GROUND_MAC" --ground-kind mac \
    --va-base 0 \
    --out-json "$WORK/boundary_mac_ghidra.json" \
    || warn "mac boundary (ghidra-only) 計算に失敗"
  warn "RetDec mac dsm がありません (macbound.drc.dsm)"
else
  warn "mac 側の boundary 計算には Ghidra slice 成果物 + function starts が必要"
fi

# EasyFLAC (300KB級, 全 pipeline 完了する小規模) の 3 者照合も記録
GHIDRA_EF_CSV="$WORK/ghidra_easyflac/functions_easyflac.csv"
if [ -f "$GHIDRA_EF_CSV" ] && [ -f "$WORK/easyflac.drc.config.json" ]; then
  llvm-objdump --macho --function-starts "$WORK/easyflac_x86_64.dylib" 2>/dev/null \
    | grep '^0' > "$WORK/function_starts_easyflac.txt" \
    || warn "EasyFLAC function starts 取得失敗"
  python3 "$HERE/function_boundary.py" --label easyflac_fullpipeline \
    --ghidra-csv "$GHIDRA_EF_CSV" \
    --retdec-json "$WORK/easyflac.drc.config.json" \
    --ground "$WORK/function_starts_easyflac.txt" --ground-kind mac \
    --va-base 0 \
    --out-json "$WORK/boundary_easyflac.json" \
    || warn "EasyFLAC boundary 計算に失敗"
fi

# -----------------------------------------------------------------
log "M2 成果物が tools/m2/work/ に揃いました (REPORT.md 参照)"
exit 0
