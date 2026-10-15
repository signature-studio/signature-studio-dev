#!/usr/bin/env bash
# Stereo SC 側の実機機械語ハーネスで、P+0x9f88 の書込み (構築関数 0x1805cb150) が process 0x1805ee2a0 より前に起きることを確かめる (#5011・#4046)。
#   usage: SC_CORE=<SlateCore.core_64> bash tools/targets/freshair/ks_sc_stereo_smoke.sh [N=20] [outdir]   (既定: $RUNNER_TEMP/ks_sc_stereo_smoke)
# 手順: ctor=1 (構築 → process) と ctor=0 (構築を飛ばす対照) を fma=0/1 で実行し、行数・ERR・ctor の自己ポインタ確認を出す。判定はしない。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; L="$HERE/lift2"
CORE="${SC_CORE:-$HERE/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64}"
N="${1:-20}"; out="${2:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/ks_sc_stereo_smoke}"
[ -f "$CORE" ] || { echo "missing: $CORE (work-liftlib-targets を展開する)" >&2; exit 2; }
mkdir -p "$out"; cd "$out"
clang -O1 -w -o native_stereo "$L/native/native_stereo.c"
python3 "$L/gen_sc_smoke_scen.py" st_scen.txt "$N" 0x5C5C >/dev/null
for C in 1 0; do for F in 0 1; do
  FA_IAT_ALL=1 FA_POKES="$L/pokes.txt" ./native_stereo "$CORE" st_scen.txt "$F" "$C" > st_c${C}_n${F}.txt 2> st_c${C}_n${F}.err
  echo "Stereo ctor=$C fma=$F rows=$(grep -c '' st_c${C}_n${F}.txt) ERR=$(grep -c ' |ERR' st_c${C}_n${F}.txt) CTOR_NOSELF=$(grep -c CTOR_NOSELF st_c${C}_n${F}.txt) stderr=$(grep -v '^$' st_c${C}_n${F}.err | tail -1)"
done; done
