#!/usr/bin/env bash
# SC 側の実機機械語ハーネス (Delay / Disperser / Phaser / QuickEq) が小さいシナリオで動くかを確かめる (#3740 / FA-44)。判定はしない (ERR 件数と行数だけ出す)。
#   usage: bash tools/targets/freshair/ks_fa44_native_smoke.sh [N=20] [outdir]   (既定: $RUNNER_TEMP/ks_fa44_smoke)
# 手順: mlift の report から iat_slots を作る (ks_sc_native_smoke.sh と同じ root・map・pokes)、シナリオを生成、fma=0/1 で native 実行。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; L="$HERE/lift2"
CORE="${SC_CORE:-$HERE/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64}"
N="${1:-20}"; out="${2:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/ks_fa44_smoke}"
[ -f "$CORE" ] || { echo "missing: $CORE (work-liftlib-targets を展開する)" >&2; exit 2; }
mkdir -p "$out"; cd "$out"
set +e; source "$L/env.sh"; set -e  # env.sh は emsdk を読むが、この smoke は emsdk を使わない。emsdk の無い環境では読み込みの失敗だけ無視する
POKES=(); while read -r va sz val; do [[ "$va" == \#* || -z "$va" ]] && continue; POKES+=(--poke "$va:$sz:$val"); done < "$L/pokes.txt"
CLASSES="delay:0x180ba8ad0 disperser:0x180be1500 phaser:0x180a1bef0 quickeq:0x180ac5550"
python3 "$L/gen_fa44_scen.py" fa44_scen.txt "$N" 0xFA44 >/dev/null
for spec in $CLASSES; do
  c="${spec%%:*}"; root="${spec#*:}"
  clang -O1 -w -o "native_$c" "$L/native/native_$c.c"
  python3 "$L/mlift/mlift.py" "$CORE" "$c.ll" \
    --root "$root:void(i64,i64)" --map 0x181030490=fa_memmove --map 0x18106a3a0=fa_mxcsr_get --map 0x18106a3ba=fa_mxcsr_set \
    --stub 18103d37c --stub 18103d47c --stub 18102f728 "${POKES[@]}" --report "${c}_rep.json" >/dev/null
  python3 -c "
import json; r = json.load(open('${c}_rep.json'))
open('iat_${c}.txt', 'w').write(''.join('%s %s\n' % (k[2:], v) for k, v in r['iat_slots'].items()))"
  for F in 0 1; do
    FA_IAT="iat_$c.txt" FA_POKES="$L/pokes.txt" "./native_$c" "$CORE" fa44_scen.txt "$F" > "${c}_n$F.txt" 2> "${c}_n$F.err"
    echo "$c fma=$F rows=$(grep -c '' "${c}_n$F.txt") ERR=$(grep -c ERR "${c}_n$F.txt")"
  done
done
