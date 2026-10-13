#!/usr/bin/env bash
# dynamics_e2e.sh の判定の識別力を確認するネガティブコントロール (Fruity Limiter block 19021, 最小の閉包)。
#   NC1: final.ll の関数 1 つを壊す (定義の ret を除去) → `emcc -c` が FAIL すること (対照: 無改変は rc=0)
#   NC2: 閉包 ranges の末尾 1 range を落として再 lift → その関数 (function_<start>) が final.ll から消え、他の関数は残ること
#        (対照: 無改変の final.ll には存在する。 RetDec は 1 range から 2 define を出す場合があるため define 数の差は 1 と限らない)
# 事前: dynamics_e2e.sh を実行済み (work/batch/19021 がある)。 exit 0 = 両方 期待通り
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
B=19021
OUT=work/batch/$B
N=work/dynamics/nega; rm -rf "$N"; mkdir -p "$N/tmp"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1

emcc_rc() { ( TMPDIR="$N/tmp" emcc -c "$1" -o "$N/x.o" -w -O0 -msimd128 > "$N/emcc.log" 2>&1 ); echo $?; }

c0=$(emcc_rc "$OUT/p.final.ll")
python3 - "$OUT/p.final.ll" "$N/broken.ll" <<'PY'
import re, sys
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

[ "$c0" = 0 ] && [ "$c1" != 0 ] && [ "$h0" = 1 ] && [ "$h1" = 0 ] && [ "$d1" -lt "$d0" ] && [ "$d1" -gt 0 ] && { echo "[dynamics_nega] OK"; exit 0; }
echo "[dynamics_nega] FAIL" >&2; exit 1
