#!/usr/bin/env bash
# Stereo SC 側の実機機械語ハーネスで、P+0x9f88 の書込み (構築関数 0x1805cb150) が process 0x1805ee2a0 より前に起きることを確かめる (#5011・#4046)。
#   usage: SC_CORE=<SlateCore.core_64> bash tools/targets/freshair/ks_sc_stereo_smoke.sh [N=20] [outdir]   (既定: $RUNNER_TEMP/ks_sc_stereo_smoke)
# 手順: ctor=1 (構築 → process) と ctor=0 (構築を飛ばす対照) を fma=0/1 で実行し、行数・ERR・ctor の自己ポインタ確認を出す。判定はしない。
#       続けて FA_SELF_STORE=1 (harness が P+0x9f88 を直接書く #4046 の再現形) を mlift の iat_slots で fma=0/1 実行する。
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
# #4046 の再現形: mlift の report から iat_slots を作り、harness が P+0x9f88 を直接書く (FA_SELF_STORE=1)
set +e; source "$L/env.sh"; set -e  # env.sh は emsdk を読むが、この smoke は emsdk を使わない。emsdk の無い環境では読み込みの失敗だけ無視する
POKES=(); while read -r va sz val; do [[ "$va" == \#* || -z "$va" ]] && continue; POKES+=(--poke "$va:$sz:$val"); done < "$L/pokes.txt"
python3 "$L/mlift/mlift.py" "$CORE" st.ll \
  --root 0x1805ee2a0:'void(i64,i64)' --map 0x181030490=fa_memmove \
  --stub 18103d37c --stub 18103d47c --stub 18102f728 "${POKES[@]}" --report st_rep.json >/dev/null
python3 -c "
import json; r = json.load(open('st_rep.json'))
open('iat_st.txt', 'w').write(''.join('%s %s\n' % (k[2:], v) for k, v in r['iat_slots'].items()))"
for F in 0 1; do
  FA_SELF_STORE=1 FA_IAT=iat_st.txt FA_POKES="$L/pokes.txt" ./native_stereo "$CORE" st_scen.txt "$F" > st_n$F.txt 2> st_n$F.err
  echo "Stereo self-store fma=$F rows=$(grep -c '' st_n$F.txt) ERR=$(grep -c ' |ERR' st_n$F.txt) stderr=$(wc -c < st_n$F.err)B"
done
