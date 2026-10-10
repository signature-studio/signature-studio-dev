#!/usr/bin/env bash
# Fresh Air 事前解析 1 コマンド: 展開 → PE 構造/保護判定 → RTTI/DSP closure → Gain lift→wasm bit-exact
#   usage: bash tools/targets/freshair/analyze.sh
set -euo pipefail
FA="$(cd -- "$(dirname -- "$0")" && pwd)"; cd "$FA"
W="work/win/Fresh Air"; CORE="$W/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
bash fetch.sh
echo "== PE 構造 (shell / AAX / core) =="; python3 pe_inspect.py "$W/C__Program Files_Steinberg_VSTPlugins_Slate Digital/Fresh Air.dll" \
  "$W/C__Program Files_Common Files_Avid_Audio_Plug-Ins_Slate Digital/Fresh Air.aaxplugin/Contents/x64/Fresh Air.aaxplugin" "$CORE" | grep -E "^work|net/crypto|notable"
echo "== 高エントロピー領域 (暗号化/ラッパ検出) =="; python3 entropy_map.py "$CORE"
echo "== RTTI: FreshAir/Gain/Filter/Compressor DSP =="; python3 rtti_vtables.py "$CORE" 'freshair@@$|DspModel@|Dsp@(gain|filter|compressor)@@$' work/rtti_dsp.json | grep -E "FreshAirDsp@|GainDsp@|FilterDsp@|CompressorDsp@"
echo "== Gain::process closure =="; python3 closure.py "$CORE" 0x180afe090 --stop 0x1803ded20 | head -1
echo "== mac core (arm64) Eden 判定 =="; M="work/mac/x/4_-_Content/Library/Application Support/Slate Digital/Fresh Air/SlateCore.core/Contents/MacOS/SlateCore"
llvm-objdump --macho --section-headers "$M" | grep -E "pbootstrap|povertext|poverdata"; grep -a -o -m1 "com.paceap.eden.wrapper" "$M" | head -1
echo "== Gain lift -> wasm bit-exact =="; bash lift/gain_e2e.sh 400 | tail -3
