#!/usr/bin/env bash
# modulation_e2e.sh の各判定の識別力を確認するネガティブコントロール (対象 block 19007 = Fruity Flanger; 8 本中で最小の閉包)。
#   NC1: final.ll の関数 1 つを壊す (定義の ret を除去) → `emcc -c` が FAIL すること (対照: 無改変は rc=0)
#   NC2: 閉包 ranges の末尾 1 range を落として再 lift → その関数 (function_<start>) が final.ll から消え、他の関数は残ること
#   NC3〜NC6: judge.py / matrix_check.py / ids_crosscheck.py / modulation_e2e.sh --judge-only を合成入力で壊す (nega_gates.py)
# 事前: modulation_e2e.sh を実行済み (work/batch/19007 と work/modulation/{status8.csv,facts.json} がある)。 exit 0 = 全て期待どおり
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
B=19007
OUT=work/batch/$B
N=work/modulation/nega_lift; rm -rf "$N"; mkdir -p "$N/tmp"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1

emcc_rc() { ( TMPDIR="$N/tmp" emcc -c "$1" -o "$N/x.o" -w -O0 -msimd128 > "$N/emcc.log" 2>&1 ); echo $?; }

c0=$(emcc_rc "$OUT/p.final.ll")
python3 - "$OUT/p.final.ll" "$N/broken.ll" <<'PY'
import sys
s = open(sys.argv[1]).read()
i = s.index('\ndefine ')
j = s.index('\n}\n', i)            # 最初の関数の閉じ括弧
body = s[i:j]
k = body.rindex('\n  ret ')        # その最後の ret を除去 (終端命令欠落 = 不正 IR)
open(sys.argv[2], 'w').write(s[:i] + body[:k] + s[j:])
PY
c1=$(emcc_rc "$N/broken.ll")
echo "NC1: emcc -c  control(rc)=$c0  broken(rc)=$c1  (期待: 0 / 非0)"

R=work/closure/block$(printf %05d $B).ranges.txt
n_all=$(tr ',' '\n' < "$R" | wc -l)
LAST=$(tr ',' '\n' < "$R" | tail -n 1 | cut -d- -f1 | sed 's/^0x//')
d0=$(grep -c '^define' "$OUT/p.final.ll"); h0=$(grep -c "^define .*@function_$LAST\\b" "$OUT/p.final.ll")
tr ',' '\n' < "$R" | head -n $((n_all - 1)) | paste -sd, > "$N/ranges_minus1.txt"
bash lift/lift_ranges.sh "$FL_WIN64_DIR/extracted/block$(printf %05d $B)_PE.bin" "$N/ranges_minus1.txt" "$N/lift" p 600 > "$N/lift.log" 2>&1
d1=$(grep -c '^define' "$N/lift/p.final.ll"); h1=$(grep -c "^define .*@function_$LAST\\b" "$N/lift/p.final.ll" || true)
echo "NC2: ranges $n_all -> $((n_all - 1)), 落とした関数 function_$LAST:  control: define=$d0 present=$h0 / minus1: define=$d1 present=$h1  (期待: 1 -> 0, define 減)"

ok12=0
[ "$c0" = 0 ] && [ "$c1" != 0 ] && [ "$h0" = 1 ] && [ "$h1" = 0 ] && [ "$d1" -lt "$d0" ] && [ "$d1" -gt 0 ] && ok12=1
python3 modulation/nega_gates.py || { echo "[modulation_nega] FAIL: nega_gates (NC3-NC6)" >&2; exit 1; }
[ "$ok12" = 1 ] && { echo "[modulation_nega] OK"; exit 0; }
echo "[modulation_nega] FAIL: NC1/NC2" >&2; exit 1
