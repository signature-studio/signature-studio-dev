#!/usr/bin/env bash
# synth_e2e.sh の各検査の識別力を確認するネガティブコントロール (1 箇所を壊して FAIL することを数値で示す)。
#   NC1: final.ll の関数 1 つを壊す (定義の ret を除去) → `emcc -c` が FAIL すること (対照: 無改変は rc=0)         [FL Slayer 22433]
#   NC2: 閉包 ranges の末尾 1 range を落として再 lift → その関数 (function_<start>) が final.ll から消えること        [FL Slayer 22433]
#   NC3: final.ll の define 1 件を別名に変える → engine_defs.py の missing が +1 になること (missing_define 列の根拠)  [FL Slayer 22433]
#   NC4: 判定 (judge.py) を synth_e2e.sh --judge-only 経由で壊した CSV に当て、非 0 で終わり OK 行が出ないこと (nega_judge.py)
#   NC5: matrix_check.py / ids_crosscheck.py に壊した facts を渡し、非 0 で終わること
# 事前: synth_e2e.sh を実行済み。 exit 0 = 全て期待通り。 1 つでも外れたら exit 1 (最後に "[synth_nega] OK" は全て通ったときだけ)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
B=22433
OUT=work/batch/$B
N=work/synth/nega; rm -rf "$N"; mkdir -p "$N/tmp"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
NG=0

emcc_rc() { ( TMPDIR="$N/tmp" emcc -c "$1" -o "$N/x.o" -w -O0 -msimd128 > "$N/emcc.log" 2>&1 ) && echo 0 || echo $?; }

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
{ [ "$c0" = 0 ] && [ "$c1" != 0 ]; } || { echo "NC1 NG"; NG=$((NG+1)); }

R=work/closure/block$(printf %05d $B).ranges.txt
n_all=$(tr ',' '\n' < "$R" | wc -l)
LAST=$(tr ',' '\n' < "$R" | tail -n 1 | cut -d- -f1 | sed 's/^0x//')
d0=$(grep -c '^define' "$OUT/p.final.ll"); h0=$(grep -c "^define .*@function_$LAST\\b" "$OUT/p.final.ll")
tr ',' '\n' < "$R" | head -n $((n_all - 1)) | paste -sd, > "$N/ranges_minus1.txt"
bash lift/lift_ranges.sh "$FL_WIN64_DIR/extracted/block$(printf %05d $B)_PE.bin" "$N/ranges_minus1.txt" "$N/lift" p 600 > "$N/lift.log" 2>&1
d1=$(grep -c '^define' "$N/lift/p.final.ll"); h1=$(grep -c "^define .*@function_$LAST\\b" "$N/lift/p.final.ll" || true)
echo "NC2: ranges $n_all -> $((n_all - 1)), 落とした関数 function_$LAST:  control: define=$d0 present=$h0 / minus1: define=$d1 present=$h1  (期待: 1 -> 0, define 減)"
{ [ "$h0" = 1 ] && [ "$h1" = 0 ] && [ "$d1" -lt "$d0" ] && [ "$d1" -gt 0 ]; } || { echo "NC2 NG"; NG=$((NG+1)); }

m0=$(python3 synth/engine_defs.py "$R" "$OUT/p.final.ll" | cut -d, -f1)
sed "s/^\\(define [^@]*\\)@function_$LAST\\b/\\1@renamed_$LAST/" "$OUT/p.final.ll" > "$N/renamed.ll"
m1=$(python3 synth/engine_defs.py "$R" "$N/renamed.ll" | cut -d, -f1)
m2=$(python3 synth/engine_defs.py "$R" "$N/no_such_file.ll" | cut -d, -f1)
echo "NC3: engine_defs missing  control=$m0  define 1 件を別名化=$m1  final.ll 欠落=$m2  (期待: 0 / 1 / -1)"
{ [ "$m0" = 0 ] && [ "$m1" = 1 ] && [ "$m2" = -1 ]; } || { echo "NC3 NG"; NG=$((NG+1)); }

python3 synth/nega_judge.py || NG=$((NG+1))

python3 - "$N" <<'PY' || NG=$((NG+1))
import json, subprocess, sys
N = sys.argv[1]
F = json.load(open('work/synth/facts.json'))
M = {p['name']: p for p in json.load(open('PLUGIN_MATRIX.json'))['plugins']}
name = next(n for n, e in F.items() if e['shell'] and M[n]['lift'])
# matrix_check: 閉包の関数数を +1 (対照: 無改変は 0)
ctl = subprocess.run(['python3', 'synth/matrix_check.py'], capture_output=True, text=True)
F[name]['shell']['closure_funcs'] += 1
json.dump(F, open(N + '/facts_cf.json', 'w'))
bad = subprocess.run(['python3', 'synth/matrix_check.py', '--facts', N + '/facts_cf.json'], capture_output=True, text=True)
F[name]['shell']['closure_funcs'] -= 1
print('NC5a matrix_check  control rc=%d (%s)  closure_funcs+1 (%s) rc=%d (%s)  (期待: 0 / 非0)' % (
    ctl.returncode, ctl.stdout.strip().splitlines()[-1][:60], name, bad.returncode, bad.stdout.strip().splitlines()[-1][:60]))
ok = ctl.returncode == 0 and bad.returncode != 0
# ids_crosscheck: taint 側の ID 件数を +1 (別算法側の件数を超える → 取りこぼし判定)
name = next(n for n, e in F.items() if e['shell'] and any(k != 'dyn' for k in e['shell']['host']['ids']))
ids = F[name]['shell']['host']['ids']
k = next(k for k in ids if k != 'dyn')
ids[k] += 1000
json.dump(F, open(N + '/facts_id.json', 'w'))
ctl2 = subprocess.run(['python3', 'synth/ids_crosscheck.py'], capture_output=True, text=True)
bad2 = subprocess.run(['python3', 'synth/ids_crosscheck.py', '--facts', N + '/facts_id.json'], capture_output=True, text=True)
print('NC5b ids_crosscheck control rc=%d (%s)  ID %s の件数 +1000 (%s) rc=%d (%s)  (期待: 0 / 非0)' % (
    ctl2.returncode, ctl2.stdout.strip().splitlines()[-1], k, name, bad2.returncode, bad2.stdout.strip().splitlines()[-1]))
ok = ok and ctl2.returncode == 0 and bad2.returncode != 0
sys.exit(0 if ok else 1)
PY
[ "$NG" = 0 ] && { echo "[synth_nega] OK"; exit 0; }
echo "[synth_nega] FAIL ($NG 件が期待と不一致)" >&2; exit 1
