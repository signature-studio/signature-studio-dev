#!/usr/bin/env bash
# SC 側の実機機械語ハーネス (Compressor / Filter) が小さいシナリオで動くかを確かめる (#2739)。判定はしない (ERR 件数と行数だけ出す)。
#   usage: bash tools/targets/freshair/ks_sc_native_smoke.sh [N=20] [outdir]   (既定: $RUNNER_TEMP/ks_sc_smoke)
# 手順: mlift の report から iat_slots を作る (build_comp.sh / build_filter.sh と同じ root・map・pokes)、シナリオを生成、fma=0/1 で native 実行。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; L="$HERE/lift2"
CORE="${SC_CORE:-$HERE/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64}"
N="${1:-20}"; out="${2:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/ks_sc_smoke}"
[ -f "$CORE" ] || { echo "missing: $CORE (work-liftlib-targets を展開する)" >&2; exit 2; }
mkdir -p "$out"; cd "$out"
set +e; source "$L/env.sh"; set -e  # env.sh は emsdk を読むが、この smoke は emsdk を使わない。emsdk の無い環境では読み込みの失敗だけ無視する
POKES=(); while read -r va sz val; do [[ "$va" == \#* || -z "$va" ]] && continue; POKES+=(--poke "$va:$sz:$val"); done < "$L/pokes.txt"
clang -O1 -w -o native_comp "$L/native/native_comp.c"
clang -O1 -w -o native_filter "$L/native/native_filter.c"
python3 "$L/gen_comp_scen.py" comp_scen.txt "$N" 0xC0FFEE >/dev/null
python3 "$L/gen_filter_scen.py" filter_scen.txt "$N" 0xF117E4 >/dev/null
# name: Compressor (root 0x180775220) / Filter (root 0x180b6f050)。mlift は build_*.sh と同じ引数で report だけ作る
python3 "$L/mlift/mlift.py" "$CORE" comp.ll \
  --root 0x180775220:'void(i64,i64)' --root 0x18103fd60:'f32(f32,f32)' \
  --map 0x181030490=fa_memmove --map 0x18106a3a0=fa_mxcsr_get --map 0x18106a3ba=fa_mxcsr_set \
  --stub 18103d37c --stub 18103d47c --stub 18102f728 "${POKES[@]}" --report comp_rep.json >/dev/null
python3 "$L/mlift/mlift.py" "$CORE" filter.ll \
  --root 0x180b6f050:'void(i64,i64)' --root 0x180b6f390:'void(i64)' --map 0x181030490=fa_memmove \
  --stub 18103d37c --stub 18103d47c --stub 18102f728 "${POKES[@]}" --report filter_rep.json >/dev/null
for n in comp filter; do
  python3 -c "
import json; r = json.load(open('${n}_rep.json'))
open('iat_${n}.txt', 'w').write(''.join('%s %s\n' % (k[2:], v) for k, v in r['iat_slots'].items()))"
done
for F in 0 1; do
  FA_IAT=iat_comp.txt FA_POKES="$L/pokes.txt" ./native_comp "$CORE" comp_scen.txt "$F" > comp_n$F.txt 2> comp_n$F.err
  echo "Compressor fma=$F rows=$(grep -c '' comp_n$F.txt) ERR=$(grep -c ERR comp_n$F.txt)"
  FA_IAT=iat_filter.txt FA_POKES="$L/pokes.txt" ./native_filter "$CORE" filter_scen.txt "$F" > f_n$F.txt 2> f_n$F.err
  echo "Filter fma=$F rows=$(grep -c '' f_n$F.txt) ERR=$(grep -c ERR f_n$F.txt)"
done
