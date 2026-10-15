#!/usr/bin/env bash
# SC 側の実機機械語ハーネス (Stereo 0x1805ee2a0) が小さいシナリオで動くかを確かめる (#3741・#4046)。判定はしない (ERR 件数と行数だけ出す)。
#   usage: bash tools/targets/freshair/ks_sc_stereo_smoke.sh [N=20] [outdir]   (既定: $RUNNER_TEMP/ks_sc_stereo_smoke)
# 注: P+0x9f88 は自己ポインタ (書き手 0x1805ec9f0)。harness が P の確保直後に書く。
# 手順: mlift の report から iat_slots を作る (ks_sc_vf_smoke.sh と同じ)、シナリオを生成、fma=0/1 で native 実行。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; L="$HERE/lift2"
CORE="${SC_CORE:-$HERE/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64}"
N="${1:-20}"; out="${2:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/ks_sc_stereo_smoke}"
[ -f "$CORE" ] || { echo "missing: $CORE (work-liftlib-targets を展開する)" >&2; exit 2; }
mkdir -p "$out"; cd "$out"
set +e; source "$L/env.sh"; set -e  # env.sh は emsdk を読むが、この smoke は emsdk を使わない。emsdk の無い環境では読み込みの失敗だけ無視する
POKES=(); while read -r va sz val; do [[ "$va" == \#* || -z "$va" ]] && continue; POKES+=(--poke "$va:$sz:$val"); done < "$L/pokes.txt"
clang -O1 -w -o native_st "$L/native/native_stereo.c"
python3 "$L/gen_sc_smoke_scen.py" st_scen.txt "$N" 0x5C5C >/dev/null
python3 "$L/mlift/mlift.py" "$CORE" st.ll \
  --root 0x1805ee2a0:'void(i64,i64)' --map 0x181030490=fa_memmove \
  --stub 18103d37c --stub 18103d47c --stub 18102f728 "${POKES[@]}" --report st_rep.json >/dev/null
python3 -c "
import json; r = json.load(open('st_rep.json'))
open('iat_st.txt', 'w').write(''.join('%s %s\n' % (k[2:], v) for k, v in r['iat_slots'].items()))"
for F in 0 1; do
  FA_IAT=iat_st.txt FA_POKES="$L/pokes.txt" ./native_st "$CORE" st_scen.txt "$F" > st_n$F.txt 2> st_n$F.err
  echo "Stereo fma=$F rows=$(grep -c '' st_n$F.txt) ERR=$(grep -c ERR st_n$F.txt) stderr=$(wc -c < st_n$F.err)B"
done
