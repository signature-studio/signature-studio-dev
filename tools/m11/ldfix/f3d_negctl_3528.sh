#!/usr/bin/env bash
# f3d_negctl_3528.sh — #3528 突合 (f3d_crosscheck_3528.py) のネガティブコントロール。
#   F3d 版 IR の function_45b170 の挿入 load の基底 `inttoptr i64 %arg2` を `%arg1` に書き換え、
#   突合が 45b170 だけ NG にすることを確かめる。判定が効くなら NG 1、効かなければ NG 0。
#   期待値: 最終行 `# changed=58 OK=57 NG=1`、NG の行は 45b170 のみ。
# 使い方: bash tools/m11/ldfix/f3d_negctl_3528.sh
# 環境変数: M11_WORK (既定 tools/m11/work) / FL_WIN64_DIR (既定 $RUNNER_TEMP/fl-win64) / PY / OUT
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
W="${M11_WORK:-$REPO/tools/m11/work}"
PE="${FL_WIN64_DIR:-${RUNNER_TEMP:-/tmp}/fl-win64}/extracted/block00031_PE.bin"
OUT="${OUT:-${RUNNER_TEMP:-/tmp}/f3d_negctl_3528}"
PY="${PY:-python3}"
mkdir -p "$OUT"
"$PY" "$HERE/ldfix.py" "$W/boot_final3.ll" "$OUT/f3d.ll" --pe "$PE" --passes f3d --report "$OUT/f3d.json" >/dev/null 2>&1 \
  || { echo "[f3d] ldfix 失敗"; exit 1; }
"$PY" - "$OUT/f3d.ll" "$OUT/f3d_nc.ll" "$HERE" <<'EOF' || { echo "[nc] mutate 失敗"; exit 1; }
import re, sys
sys.path.insert(0, sys.argv[3])
import f3d_crosscheck_3528 as X
src = open(sys.argv[1], errors='replace').read()
body = X.bodies(src)['function_45b170']
pat = re.compile(r'(%ldfxt\d+_p = inttoptr i\d+ )%arg2( to ptr)')
assert len(pat.findall(body)) == 1, 'inserted load of 45b170 is not unique'
assert src.count(body) == 1
open(sys.argv[2], 'w').write(src.replace(body, pat.sub(r'\g<1>%arg1\2', body)))
EOF
"$PY" "$HERE/f3d_crosscheck_3528.py" "$W/boot_final3.ll" "$OUT/f3d_nc.ll" --pe "$PE" --report "$OUT/f3d.json" > "$OUT/nc.tsv" \
  || { echo "[nc] 突合 失敗"; exit 1; }
tail -n 3 "$OUT/nc.tsv"
ng="$(awk -F'\t' '$NF == "NG" {print $1}' "$OUT/nc.tsv" | tr '\n' ' ')"
echo "NG 行: ${ng:-none}"
if [ "$(grep -c '^# changed=58 OK=57 NG=1$' "$OUT/nc.tsv")" = 1 ] && [ "$ng" = "45b170 " ]; then
  echo "NC PASS (NG 1: 45b170)"
else
  echo "NC FAIL"
  exit 1
fi
