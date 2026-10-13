#!/usr/bin/env bash
# hostx_e2e.sh の判定の識別力を確認するネガティブコントロール。 事前: hostx_e2e.sh 実行済み (work/batch/ と work/hostx/ がある)。 exit 0 = 全部 期待どおり
#   NC1: MIDI Out (block 23918, 最小閉包) の final.ll の関数 1 つの ret を除去 → `emcc -c` が FAIL (対照: 無改変は rc 0)
#   NC2: 閉包 ranges の末尾 1 range を落として再 lift → その関数が final.ll から消える (対照: 無改変には存在)
#   NC3: judge.py — 実測 status (declares_unimpl=0 が全 7 本) は許可名の有無によらず通す (期待 rc 0) /
#        declares_unimpl=1 の合成行 (Wrapper 19091; 名前の根拠 p.simd.log は 0 件) は 許可名なし・許可名違いで落とす (期待 rc 1) /
#        許可名ありでも emcc_c_rc=1 の合成行 (期待 rc 1) / 行を落とす (期待 rc 1)
#   NC4: expect_state.py — 実測 (期待 rc 0) / ReWired の行を合格値 (f80=0, emcc_c_rc=0) にした合成 CSV (期待 rc 1 = 方針表の更新が必要)
#   NC6: icall_audit.py — MIDI Out の final.ll の先頭関数に間接 call (inttoptr → call ptr) を 1 本注入 → audit_icall の IR 間接 call が基準から +1 / grep 側 (callee に @ が無い call 行) は 基準 0 → 注入 1
#   NC5: matrix_check.py — facts.json の 1 項目 (Patcher(E) closure_bytes) を書き換えた合成 facts (期待 rc 1)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
B=23918
OUT=work/batch/$B
N=work/hostx/nega; rm -rf "$N"; mkdir -p "$N/tmp"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
emcc_rc() { ( TMPDIR="$N/tmp" emcc -c "$1" -o "$N/x.o" -w -O0 -msimd128 > "$N/emcc.log" 2>&1 ); echo $?; }

c0=$(emcc_rc "$OUT/p.final.ll")
python3 - "$OUT/p.final.ll" "$N/broken.ll" <<'PY'
import sys
s = open(sys.argv[1]).read()
i = s.index('\ndefine ')
j = s.index('\n}\n', i)
body = s[i:j]
k = body.rindex('\n  ret ')
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

ST=work/batch/status.csv
MUST=(19091 23676 19220 24155 23918 19244 23674)
j() { local rc=0; python3 hostx/judge.py "$@" > "$N/j.out" 2>&1 || rc=$?; echo "$rc"; }
r_ok=$(j "$ST" "${MUST[@]}" --allow-unimpl rep_stosb_memset)
r_real_noallow=$(j "$ST" "${MUST[@]}")
python3 - "$ST" "$N/st_emcc.csv" "$N/st_drop.csv" "$N/st_unimpl.csv" <<'PY'
import csv, sys
rows = list(csv.reader(open(sys.argv[1], newline='')))
hdr = rows[0]; ix = {c: i for i, c in enumerate(hdr)}
last = {}
for r in rows[1:]:
    last[r[0]] = r
body = [list(last[b]) for b in ('19091', '23676', '19220', '24155', '23918', '19244', '23674')]
b2 = [list(r) for r in body]; b2[0][ix['emcc_c_rc']] = '1'
csv.writer(open(sys.argv[2], 'w', newline='')).writerows([hdr] + b2)
csv.writer(open(sys.argv[3], 'w', newline='')).writerows([hdr] + body[:-1])
b3 = [list(r) for r in body]; b3[0][ix['declares_unimpl']] = '1'
csv.writer(open(sys.argv[4], 'w', newline='')).writerows([hdr] + b3)
PY
r_noallow=$(j "$N/st_unimpl.csv" "${MUST[@]}")
r_wrongname=$(j "$N/st_unimpl.csv" "${MUST[@]}" --allow-unimpl some_other_helper)
r_emcc=$(j "$N/st_emcc.csv" "${MUST[@]}" --allow-unimpl rep_stosb_memset)
r_drop=$(j "$N/st_drop.csv" "${MUST[@]}" --allow-unimpl rep_stosb_memset)
echo "NC3: judge rc: 実測+許可名=$r_ok (期待0) / 実測・許可名なし=$r_real_noallow (期待0: declares_unimpl=0) / declares_unimpl=1 合成・許可名なし=$r_noallow (期待1) / 同・許可名違い=$r_wrongname (期待1) / emcc_c_rc=1 合成=$r_emcc (期待1) / 行欠落=$r_drop (期待1)"

e_ok=0; python3 hostx/expect_state.py "$ST" 24161 19304 > "$N/e.out" 2>&1 || e_ok=$?
python3 - "$ST" "$N/st_rewired_ok.csv" <<'PY'
import csv, sys
rows = list(csv.reader(open(sys.argv[1], newline='')))
hdr = rows[0]; ix = {c: i for i, c in enumerate(hdr)}
out = [hdr]
for r in rows[1:]:
    r = list(r)
    if r[0] == '24161':
        r[ix['f80_funcs']] = '0'; r[ix['emcc_c_rc']] = '0'
    out.append(r)
csv.writer(open(sys.argv[2], 'w', newline='')).writerows(out)
PY
e_flip=0; python3 hostx/expect_state.py "$N/st_rewired_ok.csv" 24161 19304 > "$N/e2.out" 2>&1 || e_flip=$?
echo "NC4: expect_state rc: 実測=$e_ok (期待0) / ReWired を合格値にした合成=$e_flip (期待1)"

python3 - <<'PY'
import json, os
P = 'work/hostx'
f = json.load(open(os.path.join(P, 'facts.json')))
f['plugins']['Patcher (Effects)']['closure_bytes'] += 1
json.dump(f, open(os.path.join(P, 'nega', 'facts_bad.json'), 'w'))
PY
m_ok=0; python3 hostx/matrix_check.py > "$N/m.out" 2>&1 || m_ok=$?
m_bad=0; python3 hostx/matrix_check.py "$N/facts_bad.json" > "$N/m2.out" 2>&1 || m_bad=$?
echo "NC5: matrix_check rc: 実測=$m_ok (期待0) / closure_bytes を +1 した合成=$m_bad (期待1)  [$(grep -c MISMATCH "$N/m2.out") MISMATCH 行]"

python3 - "$OUT/p.final.ll" "$N/inj/batch/$B/p.final.ll" <<'PY'
import os, sys
s = open(sys.argv[1]).read()
i = s.index('\ndefine ')
k = s.index('\n  ret ', i)
s = s[:k] + '\n  %nc_f = inttoptr i64 0 to ptr\n  call void %nc_f()' + s[k:]
os.makedirs(os.path.dirname(sys.argv[2]), exist_ok=True)
open(sys.argv[2], 'w').write(s)
PY
mkdir -p "$N/inj/closure"; cp "work/closure/block$(printf %05d $B).ranges.txt" "$N/inj/closure/"
python3 - "$N/inj" <<'PY' > "$N/icall_inj.out"
import re, subprocess, sys, json, os
inj = sys.argv[1]; B = 23918
ir = os.path.join(inj, 'batch', str(B), 'p.final.ll')
calls = [l for l in open(ir) if re.match(r'\s+(%[\w.]+ = )?(tail )?call ', l)]
print('grep_no_at=%d' % sum(1 for l in calls if '@' not in l))
PY
i_base=$(python3 -c "import json;print(json.load(open('work/hostx/icall/$B.icall.json'))['ir_call_ind_total'])")
g_base=$(python3 - "$OUT/p.final.ll" <<'PY'
import re, sys
print(sum(1 for l in open(sys.argv[1]) if re.match(r'\s+(%[\w.]+ = )?(tail )?call ', l) and '@' not in l))
PY
)
fl="work/hostx/icall/$B.funcs"
python3 ../icall/audit_icall.py --pe "$FL_WIN64_DIR/extracted/block$(printf %05d $B)_PE.bin" --ir "$N/inj/batch/$B/p.final.ll" --funcs "$fl" --json "$N/inj.icall.json" --label inj > /dev/null
i_inj=$(python3 -c "import json;print(json.load(open('$N/inj.icall.json'))['ir_call_ind_total'])")
g_inj=$(sed -n 's/^grep_no_at=//p' "$N/icall_inj.out")
echo "NC6: IR 間接 call(audit_icall) 基準=$i_base / 注入=$i_inj (期待: 差分 +1), grep 側 基準=$g_base / 注入=$g_inj (期待 0 / 1)"

[ "$c0" = 0 ] && [ "$c1" != 0 ] && [ "$h0" = 1 ] && [ "$h1" = 0 ] && [ "$d1" -lt "$d0" ] && [ "$d1" -gt 0 ] \
 && [ "$r_ok" = 0 ] && [ "$r_real_noallow" = 0 ] && [ "$r_noallow" = 1 ] && [ "$r_wrongname" = 1 ] && [ "$r_emcc" = 1 ] && [ "$r_drop" = 1 ] \
 && [ "$e_ok" = 0 ] && [ "$e_flip" = 1 ] && [ "$m_ok" = 0 ] && [ "$m_bad" = 1 ] && [ $((i_inj - i_base)) = 1 ] && [ "$g_base" = 0 ] && [ "$g_inj" = 1 ] && { echo "[hostx_nega] OK"; exit 0; }
echo "[hostx_nega] FAIL" >&2; exit 1
