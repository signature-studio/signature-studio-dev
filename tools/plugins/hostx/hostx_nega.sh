#!/usr/bin/env bash
# hostx_e2e.sh の判定の識別力を確認するネガティブコントロール。 事前: hostx_e2e.sh 実行済み (work/batch/ と work/hostx/ がある)。 exit 0 = 全部 期待どおり
#   NC1: MIDI Out (block 23918, 最小閉包) の final.ll の関数 1 つの ret を除去 → `emcc -c` が FAIL (対照: 無改変は rc 0)
#   NC2: 閉包 ranges の末尾 1 range を落として再 lift → その関数が final.ll から消える (対照: 無改変には存在)
#   NC3: judge.py — 実測 status を --allow-unimpl 付きで通す (期待 rc 0) / 許可名を変える (期待 rc 1: Wrapper の未実装 helper を許可外にする) /
#        許可名ありでも emcc_c_rc=1 の合成行 (期待 rc 1) / 行を落とす (期待 rc 1)
#   NC4: expect_state.py — 実測 (期待 rc 0) / ReWired の行を合格値 (f80=0, emcc_c_rc=0) にした合成 CSV (期待 rc 1 = 方針表の更新が必要)
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
r_noallow=$(j "$ST" "${MUST[@]}")
r_wrongname=$(j "$ST" "${MUST[@]}" --allow-unimpl some_other_helper)
python3 - "$ST" "$N/st_emcc.csv" "$N/st_drop.csv" <<'PY'
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
PY
r_emcc=$(j "$N/st_emcc.csv" "${MUST[@]}" --allow-unimpl rep_stosb_memset)
r_drop=$(j "$N/st_drop.csv" "${MUST[@]}" --allow-unimpl rep_stosb_memset)
echo "NC3: judge rc: 実測+許可名=$r_ok (期待0) / 許可名なし=$r_noallow (期待1: Wrapper の rep_stosb_memset) / 許可名違い=$r_wrongname (期待1) / emcc_c_rc=1 合成=$r_emcc (期待1) / 行欠落=$r_drop (期待1)"

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

[ "$c0" = 0 ] && [ "$c1" != 0 ] && [ "$h0" = 1 ] && [ "$h1" = 0 ] && [ "$d1" -lt "$d0" ] && [ "$d1" -gt 0 ] \
 && [ "$r_ok" = 0 ] && [ "$r_noallow" = 1 ] && [ "$r_wrongname" = 1 ] && [ "$r_emcc" = 1 ] && [ "$r_drop" = 1 ] \
 && [ "$e_ok" = 0 ] && [ "$e_flip" = 1 ] && [ "$m_ok" = 0 ] && [ "$m_bad" = 1 ] && { echo "[hostx_nega] OK"; exit 0; }
echo "[hostx_nega] FAIL" >&2; exit 1
