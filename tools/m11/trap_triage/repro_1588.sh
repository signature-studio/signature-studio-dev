#!/usr/bin/env bash
# #1588 (LD-55): m11 wasm_trap OOB 残 2 件 (0x6525b0 非到達 / 0x66ea90 不再現) の再現手順。
#   前提: FL_WIN64_DIR (fl-win64 展開先)・work-m11 / work-liftdiff 展開済み (tools/m11/work, tools/liftdiff/work)。
#   出力: tools/liftdiff/work/m11_1588/ (gitignore)。
#   usage: bash tools/m11/trap_triage/repro_1588.sh
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/../../.." && pwd)"; cd "$HERE"
: "${FL_WIN64_DIR:?FL_WIN64_DIR を設定 (fl-win64 の展開先)}"
export LD_M11_PE="${LD_M11_PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
OUT="$HERE/tools/liftdiff/work/m11_1588"
mkdir -p "$OUT"
cd tools/liftdiff
run() { # va pattern tag
  timeout 120 python3 liftdiff.py run targets/m11.json --fn "$1" --pattern "$2" --nobuild --state auto --json "$OUT/$3.json" -v > "$OUT/$3.log" 2>&1
  echo "$3 rc=$? $(grep -m1 'verdict=' "$OUT/$3.log" | cut -c1-120)"
}
run 0x6525b0 p01 0x6525b0_p01
run 0x66ea90 z 0x66ea90_z_1
run 0x66ea90 z 0x66ea90_z_2
python3 "$HERE/tools/m11/trap_triage/diverge_1588.py" "$OUT/0x6525b0_p01.json"
