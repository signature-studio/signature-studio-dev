#!/usr/bin/env bash
# SC 側の実機機械語ハーネス (Limiter) が小さいシナリオで動くかを確かめる (#3739 / FA-43)。判定はしない (ERR 件数と行数だけ出す)。
#   usage: bash tools/targets/freshair/ks_sc_native_smoke_limiter.sh [N=20] [outdir]   (既定: $RUNNER_TEMP/ks_sc_smoke_limiter)
# 手順: mlift の report から iat_slots を作る (build_filter.sh と同じ map・stub・pokes)、シナリオを生成、fma=0/1 で native 実行。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; L="$HERE/lift2"
CORE="${SC_CORE:-$HERE/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64}"
N="${1:-20}"; out="${2:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/ks_sc_smoke_limiter}"
[ -f "$CORE" ] || { echo "missing: $CORE (work-liftlib-targets を展開する)" >&2; exit 2; }
mkdir -p "$out"; cd "$out"
set +e; source "$L/env.sh"; set -e  # env.sh は emsdk を読むが、この smoke は emsdk を使わない。emsdk の無い環境では読み込みの失敗だけ無視する
POKES=(); while read -r va sz val; do [[ "$va" == \#* || -z "$va" ]] && continue; POKES+=(--poke "$va:$sz:$val"); done < "$L/pokes.txt"
clang -O1 -w -o native_limiter "$L/native/native_limiter.c"
python3 "$L/gen_limiter_scen.py" scen.txt "$N" 0x43 >/dev/null
# root: Limiter 0x18094d9c0。mlift は report だけ作る
for pair in limiter:0x18094d9c0; do
  n="${pair%%:*}"; root="${pair#*:}"
  python3 "$L/mlift/mlift.py" "$CORE" "$n.ll" \
    --root "$root":'void(i64,i64)' --map 0x181030490=fa_memmove \
    --stub 18103d37c --stub 18103d47c --stub 18102f728 "${POKES[@]}" --report "${n}_rep.json" >/dev/null
  python3 -c "
import json; r = json.load(open('${n}_rep.json'))
open('iat_${n}.txt', 'w').write(''.join('%s %s\n' % (k[2:], v) for k, v in r['iat_slots'].items()))"
done
for F in 0 1; do
  FA_IAT=iat_limiter.txt FA_POKES="$L/pokes.txt" ./native_limiter "$CORE" scen.txt "$F" > limiter_n$F.txt 2> limiter_n$F.err
  echo "Limiter fma=$F rows=$(grep -c '' limiter_n$F.txt) ERR=$(grep -c ERR limiter_n$F.txt)"
done
