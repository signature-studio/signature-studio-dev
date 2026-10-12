#!/usr/bin/env bash
# reproduce.sh — regenerate evidence/* (Ghidra decompile excerpts of FLEngine_x64.dll 26.1.7 + constant tables) from the installer extract.
#   needs: tools/m2/work/ghidra_dll (FLEngine Ghidra project, copied to nfo/work/ghidra_fle), pefile (python3).
set -euo pipefail
NFO="$(cd -- "$(dirname -- "$0")/.." && pwd)"
HB="$NFO/.."; W="$NFO/work"; E="$NFO/evidence"
source "$NFO/../../shared/env.sh"
FLE_PE="$FL_WIN64_DIR/extracted/block00031_PE.bin"   # FLEngine_x64.dll 26.1.7.5653
mkdir -p "$W/tmp" "$E"
export _JAVA_OPTIONS="-Djava.io.tmpdir=$W/tmp"
[ -d "$W/ghidra_fle" ] || cp -r "$HB/../m2/work/ghidra_dll" "$W/ghidra_fle"
Q() { local out="$1"; shift; "$HB/ghidra_scripts/run.sh" "$W/ghidra_fle" ghproj_dll block00031_PE.bin "$W/$out" "$@" > /dev/null; python3 "$NFO/analysis/strip_decls.py" "$W/$out" "$E/$out"; }
# entry reader/writer + the INI-ish value file
Q fle_entry_rw.c    decomp 910cd0 910810 911940 911e10 912d10 913f40 abe970
Q fle_valuefile.c   decomp 913450 913be0 913d40 913a10 9139f0 913ae0 913960 913980 913cd0 9138a0 914780 914880 913e60 913ea0 913f10 914690 914700 914800 913e30 913720 913360 65de10 4391c0 439300 910590 910530 63b830 63b800
# classes / slots / folders / names / tokens
Q fle_classes.c     decomp 8ef860 8f0300 8f0ab0 8f0bc0 8f6990 8f0740 8f19b0 8f1820 8f0c20 8f0d30 8f1110 8f6dc0 8f6380 8f64f0 8f6110 8f6050 8f6560 8f5cd0 8f49e0 8f4b50
# locate / store / VerifiedIDs / .Plugins.ini / New
Q fle_locate_store.c decomp 8f05d0 8f15a0 8f5d00 9155c0 915750 916490 916710 916280 916620 914a20 914ca0 915220 90f100 ab9f40 aba1b0 abb7d0 abb500 abb620 abba70 abaf70 abc0f0 ab8310 ab9150 ab8e60 ab9200 ab9b10 aba430 abf130
# wrapper .fst writer
Q fle_wrapper_fst.c decomp aba880 ab8ae0 aac300 aac1e0 a9eff0 8e8ed0 8e8fe0 8e8e10 661970 8ef610
"$HB/ghidra_scripts/run.sh" "$W/ghidra_fle" ghproj_dll block00031_PE.bin "$E/fle_wrapper_chunk.asm" disasm a9eff0 > /dev/null
python3 "$NFO/analysis/dump_tables.py" "$FLE_PE" > "$E/fle_tables.txt"
echo "[reproduce] evidence → $E"
