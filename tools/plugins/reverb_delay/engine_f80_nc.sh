#!/usr/bin/env bash
# engine_f80_gate.sh の負の対照 (NC)。 emcc は呼ばない (gate には rc=0 を渡し、FAIL が除外集合の差に由来することだけを見る)。
#   bash tools/plugins/reverb_delay/engine_f80_nc.sh <FULL.ll | synth> <OUTDIR>
#   FULL.ll: engine_lift.sh の e.fixcmp.ll 形式 / synth: 誤除外の再現用の合成 IR (本体に f80 を持たない define の直後に x86_fp80 の declare)
# 期待: base=PASS、nc1 (件数を保ったまま非 f80 関数を 1 件だけ除外名に入れる = 旧 gate が見逃す型)=FAIL、nc2 (除外を 1 件減らす)=FAIL。 全て満たせば exit 0。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
IN="$1"; D="$2"; mkdir -p "$D"
if [ "$IN" = synth ]; then
  IN="$D/synth.ll"
  printf '%s\n' \
    'define dso_local i32 @function_1000(i32 %a) {' \
    '  ret i32 %a' \
    '}' \
    'declare void @__frontend_reg_load.fpr(x86_fp80*)' \
    'define dso_local void @function_1800bcb00(x86_fp80 %x) {' \
    '  %y = fadd x86_fp80 %x, %x' \
    '  ret void' \
    '}' > "$IN"
fi
python3 "$HERE/engine_f80_stub.py" "$IN" "$D/sub.ll" "$D/excl.tsv" || exit 2
defs() { awk '/^define /{n=$0; sub(/^[^@]*@/,"",n); sub(/\(.*/,"",n); print n}' "$1" | sort; }
N0=$(comm -23 <(defs "$IN") <(tail -n +2 "$D/excl.tsv" | cut -f1 | sort) | head -1)
{ head -1 "$D/excl.tsv"; printf '%s\tNA\tNC1: 非 f80 関数を除外名に入れた\n' "$N0"; tail -n +3 "$D/excl.tsv"; } > "$D/nc1.tsv"
head -n -1 "$D/excl.tsv" > "$D/nc2.tsv"
bash "$HERE/engine_f80_gate.sh" "$IN" "$D/sub.ll" "$D/excl.tsv" 0 | sed 's/^/base /'; b=${PIPESTATUS[0]}
bash "$HERE/engine_f80_gate.sh" "$IN" "$D/sub.ll" "$D/nc1.tsv" 0 | sed 's/^/nc1  /'; n1=${PIPESTATUS[0]}
bash "$HERE/engine_f80_gate.sh" "$IN" "$D/sub.ll" "$D/nc2.tsv" 0 | sed 's/^/nc2  /'; n2=${PIPESTATUS[0]}
echo "nc1 excluded name: $N0"
[ "$b" -eq 0 ] && [ "$n1" -ne 0 ] && [ "$n2" -ne 0 ]
