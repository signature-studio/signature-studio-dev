#!/bin/bash
# One-command e2e for tools/targets/serum2: extract installers -> binary survey -> protection indicators -> census.
# usage: bash scripts/run_all.sh            (static analysis only, ~1 min after extraction)
#        GHIDRA=1 bash scripts/run_all.sh   (also runs Ghidra headless full analysis: 10-40 min)
# inputs : ~/ダウンロード/Install_Xfer_Serum2_2.1.5.exe, "Xfer Serum2 v2.1.5.pkg"
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"; cd "$HERE"
DL="${DL:-$HOME/ダウンロード}"; W=work; O=out
mkdir -p $W/exe_extract $W/pkg_extract $W/mac_bin $O

# 1. Windows installer: NSIS-3 Unicode, plain 7z
if [ ! -f $W/exe_extract.done ]; then
  rm -rf $W/exe_extract; mkdir -p $W/exe_extract
  7z x -y -o$W/exe_extract "$DL/Install_Xfer_Serum2_2.1.5.exe" > $W/exe_extract.log 2>&1
  echo "exit=$?" > $W/exe_extract.done
fi
# 2. macOS pkg: xar -> per-component gzip cpio
if [ ! -f $W/pkg_extract/Distribution ]; then ( cd $W/pkg_extract && xar -xf "$DL/Xfer Serum2 v2.1.5.pkg" ); fi
for n in VST3 AU AAX Default-Skin; do
  if [ ! -d $W/pkg_extract/payload_$n ]; then
    mkdir -p $W/pkg_extract/payload_$n
    ( cd $W/pkg_extract/payload_$n && gzip -dc ../com.xfer.serum2.$n.pkg/Payload | cpio -idm --quiet ) || true
  fi
done
V3W="$W/exe_extract/\$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3"
AAXW="$W/exe_extract/\$COMMONFILES64/Avid/Audio/Plug-Ins/Serum2.aaxplugin/Contents/x64/Serum2.aaxplugin"
cp -n "$V3W" $W/Serum2_win64.vst3
M=$W/pkg_extract/payload_VST3/Serum2.vst3/Contents/MacOS/Serum2
[ -f $W/mac_bin/Serum2_vst3_x86_64 ] || llvm-lipo "$M" -thin x86_64 -output $W/mac_bin/Serum2_vst3_x86_64
[ -f $W/mac_bin/Serum2_vst3_arm64 ]  || llvm-lipo "$M" -thin arm64  -output $W/mac_bin/Serum2_vst3_arm64

# 3. binaries
python3 scripts/pe_survey.py $W/Serum2_win64.vst3 "$AAXW" > $O/pe_survey.txt
llvm-objdump --section-headers $W/mac_bin/Serum2_vst3_x86_64 > $O/mac_x86_64_sections.txt
llvm-nm $W/mac_bin/Serum2_vst3_x86_64 > $W/mac_bin/nm_x64.txt 2>&1 || true
llvm-objdump --macho --dylibs-used $W/mac_bin/Serum2_vst3_x86_64 > $O/mac_dylibs.txt
llvm-objdump --macho --exports-trie $W/mac_bin/Serum2_vst3_x86_64 > $O/mac_exports.txt
# 4. protection / structure
python3 scripts/protect_indicators.py $W/Serum2_win64.vst3 > $O/protect_indicators.txt
python3 scripts/crypto_scan.py $W/Serum2_win64.vst3 > $O/crypto_scan.txt
python3 scripts/rtti_classes.py $W/Serum2_win64.vst3 $W/win64_rtti > $O/rtti_summary.txt
cp $W/win64_rtti_classes.txt $O/rtti_classes.txt
# 5. census / layout
python3 scripts/text_census.py $W/Serum2_win64.vst3 $W/win64_census.json > $O/census_summary.json
python3 scripts/dsp_closure.py $W/Serum2_win64.vst3 $W/win64_closure.json > $O/closure_summary.json
python3 scripts/layout_map.py > $O/layout_map.txt
python3 scripts/fp_bands.py > $O/fp_bands.txt
python3 scripts/xref_scan.py $W/Serum2_win64.vst3 > $O/xref_scan.txt
# 6. Ghidra light pass (no auto-analysis; ~1 min): functions from .pdata + decompile of network/auth-related targets
bash scripts/ghidra_light.sh
grep -E "PDATA_FUNCS|DONE|TOTAL" $W/ghidra_light/ghidra.log > $O/ghidra_light_summary.txt || true
# optional full auto-analysis (10-40+ min, CPU heavy): GHIDRA=1
if [ "${GHIDRA:-0}" = 1 ]; then bash scripts/ghidra_win64.sh; cp $W/ghidra_out/{string_xrefs.txt,api_xrefs.txt} $O/ 2>/dev/null || true; fi
echo "run_all OK"
