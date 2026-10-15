#!/usr/bin/env bash
# reproduce.sh — Fruity Wrapper 解析の根拠 (evidence/*) を素材から再生成する.
#   素材: $FL_WIN64_DIR/extracted/blockNNNNN_PE.bin (自作 NSIS パーサ産物; tools/shared/env.sh)
#         $PLUGINS_DIR/ott/report_logs/ghidraProj (OTT Ghidra project; コピーして使用)
#         tools/m2/work/ghidra_dll (FLEngine_x64.dll の Ghidra project; コピーして使用)
#   初回は fw_a.dll の Ghidra 自動解析 (~3 分) が走る. 以降は解析済 project に対するクエリのみ (数十秒).
set -euo pipefail
HB="$(cd -- "$(dirname -- "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "$HB/../shared/env.sh"   # FL_WIN64_DIR / PLUGINS_DIR
W="$HB/work"; G="$W/ghidra"; E="$HB/evidence"; X="$FL_WIN64_DIR/extracted"
GH=/opt/ghidra/ghidra_12.1.4_PUBLIC/support/analyzeHeadless
mkdir -p "$W" "$G" "$E"
[ -f "$W/fw_a.dll" ]          || cp "$X/block19091_PE.bin" "$W/fw_a.dll"        # Fruity Wrapper 2.7.0.5653 (x64)
[ -f "$W/ilbridge64.exe" ]    || cp "$X/block24766_PE.bin" "$W/ilbridge64.exe"  # ILBridge 1.5.114 x64
[ -f "$W/pluginmanager.exe" ] || cp "$X/block25160_PE.bin" "$W/pluginmanager.exe"
if [ ! -d "$G/fw.rep" ]; then
  (cd "$W" && "$GH" ghidra fw -import fw_a.dll -scriptPath "$HB/ghidra_scripts" -postScript DumpFunctions.java "$G/functions_fw.csv" -max-cpu 8 > "$G/analyze_fw.log" 2>&1)
fi
[ -d "$W/ghidra_fle" ]  || cp -r "$HB/../m2/work/ghidra_dll" "$W/ghidra_fle"
[ -d "$W/ghidraProj.rep" ] || cp -r "$PLUGINS_DIR"/ott/report_logs/ghidraProj.* "$W/"
Q() { "$HB/ghidra_scripts/run.sh" "$@" > /dev/null; }
FW() { local out="$1"; shift; Q "$G" fw fw_a.dll "$E/$out" "$@"; }
FLE() { local out="$1"; shift; Q "$W/ghidra_fle" ghproj_dll block00031_PE.bin "$E/$out" "$@"; }
OTT() { local out="$1"; shift; Q "$W" ghidraProj OTT_vst2_win64.dll "$E/$out" "$@"; }

# --- Fruity Wrapper (VST2 host 部)
FW fw_tvstplugin_create.c   decomp 7a9db0          # TVSTPlugin.Create: LoadLibrary→FindMain→main→effOpen...
FW fw_findmain_getproc.c    decomp 7a8f90 7a8f60 449770 7ad370 7a9030 437ab0   # 26 名前表ループ / GetProcAddress ラッパ / SafeLoadLibrary / FindMain(hint) / 事前 export 検査 / 小文字化
FW fw_audiomaster.c         decomp 7a87c0          # audioMaster コールバック
FW fw_process_params.c      decomp 7ad040 7acfa0 7ac960 7afab0 7ac880   # process/getParam/setParam/paramName
FW fw_bridge_kind.c         decomp 770a80 76f3f0 76f320 7729c0 5bfe50   # bridged/native, 32/64 判定, ilbridge 起動
FW fw_pe_bitness.asm        disasm 5bfc30
FW fw_createplug_instance.c decomp 86ab10          # Fruity plugin export (FL が GetProcAddress する)
FW fw_xref_strings.txt      xrefstr "Create VST plugin" "found main function" "Call main" "32bit\\ilbridge.exe" "TBridgedPlugin.Destroy" "-wrapper" "bridged" "native"
FW fw_loadlib_callers.txt   refsto 4220d0 407020 407000 421dc0 421c10
# --- FLEngine (FL → Fruity plugin のロード)
FLE fle_load_fruity_plugin.c decomp d8cab0         # SafeLoadLibrary(path+"_x64.dll")→GetProcAddress("CreatePlugInstance")→plug->Dispatcher(...)
# --- OTT VST2 DLL (AEffect レイアウトの一次証拠)
OTT ott_audioeffect_ctor.asm    disasm 180126920
OTT ott_createeffectinstance.asm disasm 180125b40
OTT ott_vstpluginmain.asm       disasm 180128ba0
OTT ott_dispatch_effect_class.c decomp 180126c00
OTT ott_ctor_args.asm           disasm 180127550
OTT ott_ottprocessor_ctor.asm   disasm 18011d400   # OTTProcessor::OTTProcessor: AudioEffectX ctor へ numPrograms/numParams を渡す
# --- VST dispatcher opcode 集計 (Fruity Wrapper VSTPlug unit 全関数を decompile → host 側 dispatcher 呼出の opcode を抽出)
FW fw_vstplug_unit.c decompall 7a8000 7b6000
python3 "$HB/analysis/opcode_census.py" "$E/fw_vstplug_unit.c" > "$E/fw_dispatcher_opcodes.txt"
rm -f "$E/fw_vstplug_unit.c"   # 157KB: 再生成可能ゆえ commit しない
# --- 26 名前表 (0x8e5d08) の復元
python3 "$HB/analysis/dump_name_table.py" "$W/fw_a.dll" > "$E/fw_main_name_table.txt"
echo "[reproduce] evidence → $E"
