#!/usr/bin/env bash
# f3d_negctl_2745.sh — #2745 (LD-127) F3d ガードのネガティブコントロール。
#   ガード 3 種を 1 つずつ外した複製 ldfix で boot_final3.ll 全関数に --passes f3d を掛け、
#   既定 (ガードあり・none) との差を数える。外して差が出るガードは効いている。差が 0 なら、この入力では判定に効いていない。
#   unres: base 未解決の分岐で arg1 に決め打ち / load: 既存 load の検査を外す / amb: 入口 xor の一意性を外す (先頭候補を採用)
# 使い方: bash tools/m11/ldfix/f3d_negctl_2745.sh
# 環境変数: M11_WORK (既定 tools/m11/work) / FL_WIN64_DIR (既定 $RUNNER_TEMP/fl-win64) / PY / OUT
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
W="${M11_WORK:-$REPO/tools/m11/work}"
PE="${FL_WIN64_DIR:-${RUNNER_TEMP:-/tmp}/fl-win64}/extracted/block00031_PE.bin"
OUT="${OUT:-${RUNNER_TEMP:-/tmp}/f3d_negctl_2745}"
PY="${PY:-python3}"
mkdir -p "$OUT/src"
cp "$HERE"/*.py "$OUT/src/"
cp "$HERE/../lb_base.py" "$OUT/"
cat > "$OUT/mutate.py" <<'EOF'
import sys
src = open(sys.argv[1]).read()
pairs = {
    'unres': [("rep['f3d_base_unresolved'] = rep.get('f3d_base_unresolved', 0) + 1\n        return 0",
               "rep['f3d_base_unresolved'] = rep.get('f3d_base_unresolved', 0) + 1\n        argn = 1")],
    'load': [("if re.search(r'load [i0-9]+, ptr %%arg%d(?![\\w.$-])' % argn, blk_text):\n        rep['f3d_load_present']",
              "if False:\n        rep['f3d_load_present']")],
    'amb': [("if len(cands) != 1:", "if len(cands) < 1:")],
    'dist': [("rep['f3d_ambiguous'] = rep.get('f3d_ambiguous', 0) + 1",
              "rep['f3d_ambiguous_n%d' % len(cands)] = rep.get('f3d_ambiguous_n%d' % len(cands), 0) + 1")],
}[sys.argv[2]]
for a, b in pairs:
    assert src.count(a) == 1, a
    src = src.replace(a, b)
open(sys.argv[3], 'w').write(src)
EOF
cat > "$OUT/cmp.py" <<'EOF'
import json, sys
name, base, mut = sys.argv[1], json.load(open(sys.argv[2])), json.load(open(sys.argv[3]))
bv, mv = set(base['f3d_vas']), set(mut['f3d_vas'])
print('%-5s f3d_fns=%d (既定 %d) base_unresolved=%d ambiguous=%d load_present=%d added=%d removed=%d'
      % (name, mut['f3d_fns'], base['f3d_fns'], mut.get('f3d_base_unresolved', 0), mut.get('f3d_ambiguous', 0),
         mut.get('f3d_load_present', 0), len(mv - bv), len(bv - mv)))
EOF
run() {
  local m="$1" py="$HERE/ldfix.py"
  if [ "$m" != none ]; then
    py="$OUT/src/ldfix_$m.py"
    "$PY" "$OUT/mutate.py" "$HERE/ldfix.py" "$m" "$py" || { echo "[$m] mutate 失敗"; exit 1; }
  fi
  "$PY" "$py" "$W/boot_final3.ll" "$OUT/$m.ll" --pe "$PE" --passes f3d --report "$OUT/$m.json" >/dev/null 2>&1 || { echo "[$m] ldfix 失敗"; exit 1; }
}
run none
for m in unres load amb dist; do run "$m"; done
python3 -c "import json;d=json.load(open('$OUT/dist.json'));print({k:v for k,v in d.items() if k.startswith('f3d_ambiguous')})"
"$PY" "$OUT/cmp.py" none "$OUT/none.json" "$OUT/none.json"
for m in unres load amb; do
  "$PY" "$OUT/cmp.py" "$m" "$OUT/none.json" "$OUT/$m.json"
  echo "       IR 差分行 (none との diff): $(diff "$OUT/none.ll" "$OUT/$m.ll" | grep -c '^[<>]')"
done
