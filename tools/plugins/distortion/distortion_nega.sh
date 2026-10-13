#!/usr/bin/env bash
# distortion_e2e.sh の各検査が「壊したら落ちる」ことを数値で確認するネガティブコントロール。
#   NC-J : 判定 (judge.py を経由する e2e の --judge-only 経路) に不合格行を注入 → 非 0 かつ最終行 OK が出ないこと (対照: 実測 status.csv は 0 + OK)
#   NC-JE: 同 engine 判定 (--engines)
#   NC-E : final.ll の関数 1 つの ret を除去 → emcc -c が非 0 (対照 0)
#   NC-R : 閉包 ranges の末尾 1 range を落として再 lift → その関数が final.ll から消える (対照 present)
#   NC-I : ids_crosscheck.py に、独立走査の件数より多い ID 件数 (+1) を持つ facts を与える → exit 1 (対照 0)
#   NC-M : matrix_check.py に closure_funcs +1 の facts / emcc_c_rc を変えた status を与える → exit 1 (対照 0)
#   NC-W : e2e 本体 (--skip-lift) に判定が落ちる lift 結果を与える → 非 0 かつ OK 行なし
#   NC-N : unimpl_names.py に未実装名 (旧許容の rep_stosb_memset を含む) / 件数不一致 / log 無しの simd.log を与える → exit 1 (対照 0)
#   NC-D : engine_defs.py に実在しない range を 1 本足した ranges を与える → missing_define が 1 増える
# 事前: distortion_e2e.sh を実行済み。 exit 0 = 全 NC が期待通り
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
OUT=work/distortion
N=$OUT/nega; rm -rf "$N"; mkdir -p "$N/tmp"
for f in "$OUT/status.csv" "$OUT/facts.json" "$OUT/engines.csv"; do [ -f "$f" ] || { echo "[distortion_nega] 事前に distortion_e2e.sh が必要: $f が無い" >&2; exit 2; }; done
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
fail=0; total=0
chk() { total=$((total + 1)); if [ "$2" = ok ]; then echo "  $1: OK"; else echo "  $1: **NG**"; fail=$((fail + 1)); fi; }

# ---- NC-J / NC-JE: 判定の識別力 ------------------------------------------------
mut() {   # mut <name> <block> <col> <value|DEL|DUP|ADD>  → $N/<name>.csv
python3 - "$OUT/status.csv" "$N/$1.csv" "$2" "$3" "$4" <<'PY'
import csv, sys
src, dst, block, col, val = sys.argv[1:]
rows = list(csv.reader(open(src)))
hdr, body = rows[0], rows[1:]
i = hdr.index(col) if col in hdr else None
out = []
for r in body:
    if r[0] == block:
        if val == 'DEL':
            continue
        if val == 'DUP':
            out.append(list(r))
        elif val == 'ADD':
            pass
        else:
            r = list(r); r[i] = val
    out.append(r)
if val == 'ADD':
    out.append(['99999', 'Bogus'] + body[0][2:])
csv.writer(open(dst, 'w'), lineterminator='\n').writerows([hdr] + out)
PY
}
ej() {   # ej <name> [audit.csv]  → e2e の --judge-only 経路。 出力は $N/<name>.out。 echo "<rc> <OK 行の有無>"
  local o rc ok
  o=$(bash distortion/distortion_e2e.sh --judge-only "$N/$1.csv" ${2:+"$2"} 2>&1); rc=$?
  echo "$o" > "$N/$1.out"
  ok=0; echo "$o" | grep -q '^\[distortion_e2e\] OK' && ok=1
  echo "$rc $ok"
}
why() { grep -qE -- "$2" "$N/$1.out" && echo "理由一致" || echo "**理由不一致**"; }   # why <name> <regex>: 期待した理由で落ちたか
cp "$OUT/status.csv" "$N/control.csv"
read -r rc ok < <(ej control)
echo "NC-J 対照 (実測 status.csv): exit=$rc OK 行=$ok  (期待 0 / 1)"
[ "$rc" = 0 ] && [ "$ok" = 1 ] && chk 'NC-J 対照' ok || chk 'NC-J 対照' ng
while read -r nm blk col val pat; do
  mut "$nm" "$blk" "$col" "$val"
  read -r rc ok < <(ej "$nm")
  w=$(why "$nm" "$pat")
  echo "NC-J $nm: block $blk $col <- $val: exit=$rc OK 行=$ok $w [$pat]  (期待 非0 / 0 / 理由一致)"
  [ "$rc" != 0 ] && [ "$ok" = 0 ] && [ "$w" = 理由一致 ] && chk "NC-J $nm" ok || chk "NC-J $nm" ng
done <<EOF
emcc_c1 19004 emcc_c_rc 1 emcc_c_rc=1
lift_rc1 19078 lift_rc 1 lift_rc=1
f80_3 18987 f80_funcs 3 f80_funcs=3
unimpl5 19082 declares_unimpl 5 declares_unimpl=5
unimpl_was_allowed 19024 declares_unimpl 1 declares_unimpl=1
unimpl_unknown 18914 declares_unimpl -1 declares_unimpl=-1
defines0 19089 defines 0 defines=0
defines_ne_closure 18972 defines 9999 defines=9999
module_lift_rc1 18916 lift_rc 1 lift_rc=1
nonint 19004 lift_rc x 非整数
row_deleted 19004 - DEL 行数.0
row_dup 19004 - DUP 行数.2
row_extra 19004 - ADD 対象外の行
EOF
# 欠落監査の識別力: audit.csv を壊す (status.csv は無改変)
python3 - "$OUT/shell_audit.csv" "$N" <<'PY'
import csv, sys
rows = list(csv.reader(open(sys.argv[1])))
hdr, body = rows[0], rows[1:]
def w(name, blk, col, val):
    b = [list(r) for r in body]
    for r in b:
        if r[0] == blk:
            r[hdr.index(col)] = val
    csv.writer(open('%s/%s.csv' % (sys.argv[2], name), 'w'), lineterminator='\n').writerows([hdr] + b)
w('audit_missing', '19004', 'missing_define', '1')
w('audit_funcdefs', '19078', 'function_defines', str(int(next(r for r in body if r[0] == '19078')[hdr.index('function_defines')]) + 1))
w('audit_extra', '18914', 'extra_inside', '0')
PY
for nmpat in audit_missing:missing_define=1 audit_funcdefs:function_defines=16 audit_extra:extra_inside; do
  nm=${nmpat%%:*}; pat=${nmpat#*:}
  read -r rc ok < <(ej control "$N/$nm.csv"); w=$(why control "$pat")
  echo "NC-J $nm: audit 側を破壊: exit=$rc OK 行=$ok $w [$pat]  (期待 非0 / 0 / 理由一致)"
  [ "$rc" != 0 ] && [ "$ok" = 0 ] && [ "$w" = 理由一致 ] && chk "NC-J $nm" ok || chk "NC-J $nm" ng
done
sed '1s/block,name/blk,name/' "$N/control.csv" > "$N/badhdr.csv"
read -r rc ok < <(ej badhdr); w=$(why badhdr 'ヘッダ不一致')
echo "NC-J badhdr: ヘッダ破損: exit=$rc OK 行=$ok $w  (期待 2 / 0 / 理由一致)"
[ "$rc" = 2 ] && [ "$ok" = 0 ] && [ "$w" = 理由一致 ] && chk 'NC-J badhdr' ok || chk 'NC-J badhdr' ng

EB=$(python3 distortion/targets.py engines | tr ' ' ,)
je() {   # je <name> <csv> → rc
  python3 distortion/judge.py "$2" --engines --blocks "$EB" > "$N/$1.out" 2>&1; echo $?
}
python3 - "$OUT/engines.csv" "$N" <<'PY'
import csv, sys
rows = list(csv.reader(open(sys.argv[1])))
hdr, body = rows[0], rows[1:]
def w(name, f):
    b = [list(r) for r in body]; f(b)
    csv.writer(open('%s/%s.csv' % (sys.argv[2], name), 'w'), lineterminator='\n').writerows([hdr] + b)
w('e_ctrl', lambda b: None)
w('e_lift_rc1', lambda b: b[0].__setitem__(hdr.index('lift_rc'), '1'))
w('e_defines0', lambda b: b[-1].__setitem__(hdr.index('defines'), '0'))
w('e_unknown', lambda b: b[0].__setitem__(hdr.index('missing_define'), '-1'))
w('e_deleted', lambda b: b.pop(0))
w('e_emcc1', lambda b: b[0].__setitem__(hdr.index('emcc_c_rc'), '1'))
w('e_miss1', lambda b: b[-1].__setitem__(hdr.index('missing_define'), '1'))
w('e_f80', lambda b: b[0].__setitem__(hdr.index('f80_funcs'), '1'))
PY
rc=$(je e_ctrl "$N/e_ctrl.csv"); echo "NC-JE 対照 (実測 engines.csv): exit=$rc (期待 0)"; [ "$rc" = 0 ] && chk 'NC-JE 対照' ok || chk 'NC-JE 対照' ng
for nm in e_lift_rc1 e_defines0 e_unknown e_deleted e_emcc1 e_miss1 e_f80; do
  rc=$(je "$nm" "$N/$nm.csv"); echo "NC-JE $nm: exit=$rc (期待 非0)"; [ "$rc" != 0 ] && chk "NC-JE $nm" ok || chk "NC-JE $nm" ng
done
# emcc_c_rc / missing_define / f80_funcs の不合格は、その列名の理由で落ちること
for pr in e_emcc1:emcc_c_rc=1 e_miss1:missing_define=1 e_f80:f80_funcs=1; do
  nm=${pr%%:*}; pat=${pr#*:}
  if grep -q "$pat" "$N/$nm.out"; then echo "NC-JE $nm 理由 [$pat]: 一致"; chk "NC-JE $nm 理由" ok; else echo "NC-JE $nm 理由 [$pat]: 不一致"; chk "NC-JE $nm 理由" ng; fi
done

# ---- NC-C: C++ 閉包 (closure_cpp.py) — seed を断つと非 0 -------------------------------------
python3 distortion/closure_cpp.py 19101 > "$N/cc_ctrl.out" 2>&1; rc0=$?
CLOSURE_CPP_SEED_DEPTH=0 python3 distortion/closure_cpp.py 19101 > "$N/cc_bad.out" 2>&1; rc1=$?
echo "NC-C: closure_cpp 19101 対照 exit=$rc0 (期待 0) / seed 探索深さ 0 exit=$rc1 (期待 非0, 理由 seed_vtables=0)"
[ "$rc0" = 0 ] && [ "$rc1" != 0 ] && grep -q 'seed_vtables=0' "$N/cc_bad.out" && chk 'NC-C' ok || chk 'NC-C' ng

# ---- NC-N: 未実装 helper の名前 (件数だけの judge を補う) ---------------------------------
mkdir -p "$N/ub/19024" "$N/ub/19004" "$N/ub_bad/19024" "$N/ub_bad2/19004" "$N/ub_bad3/19024"
cp work/batch/19024/p.simd.log "$N/ub/19024/"; cp work/batch/19004/p.simd.log "$N/ub/19004/"
bump() { sed -E 's/(unimplemented )[0-9]+/\11/' "$1"; }   # 集計行の未実装件数を 1 にする
{ bump work/batch/19024/p.simd.log; echo '   unimplemented: void __asm_rep_stosb_memset(ptr, i8, i64)'; } > "$N/ub_bad/19024/p.simd.log"
{ bump work/batch/19004/p.simd.log; echo '   unimplemented: void __asm_fake_helper(ptr)'; } > "$N/ub_bad2/19004/p.simd.log"
bump work/batch/19024/p.simd.log > "$N/ub_bad3/19024/p.simd.log"
AL=''
python3 distortion/unimpl_names.py "$N/ub" --blocks 19024,19004 $AL > "$N/un0.out" 2>&1; rc=$?
echo "NC-N 対照 (実測 p.simd.log): exit=$rc  $(tail -n 1 "$N/un0.out")  (期待 0)"
[ "$rc" = 0 ] && chk 'NC-N 対照' ok || chk 'NC-N 対照' ng
python3 distortion/unimpl_names.py "$N/ub_bad" --blocks 19024 $AL > "$N/un1.out" 2>&1; rc=$?
echo "NC-N 旧許容 helper (rep_stosb_memset) が再び未実装: exit=$rc  (期待 1)"; [ "$rc" = 1 ] && chk 'NC-N 別名' ok || chk 'NC-N 別名' ng
python3 distortion/unimpl_names.py "$N/ub_bad2" --blocks 19004 $AL > "$N/un2.out" 2>&1; rc=$?
echo "NC-N 未実装 0 の block に未知の名前 (件数も 1 に揃える): exit=$rc  (期待 1)"; [ "$rc" = 1 ] && chk 'NC-N 追記' ok || chk 'NC-N 追記' ng
python3 distortion/unimpl_names.py "$N/ub_bad3" --blocks 19024 $AL > "$N/un3.out" 2>&1; rc=$?
echo "NC-N 件数 1 だが名前の行が無い: exit=$rc  (期待 1)"; [ "$rc" = 1 ] && chk 'NC-N 件数不一致' ok || chk 'NC-N 件数不一致' ng
python3 distortion/unimpl_names.py "$N/ub" --blocks 19024,18914 $AL > "$N/un4.out" 2>&1; rc=$?
echo "NC-N log が無い block: exit=$rc  (期待 1)"; [ "$rc" = 1 ] && chk 'NC-N log 無し' ok || chk 'NC-N log 無し' ng

# ---- NC-E / NC-R: emcc -c ゲートと ranges (最小の閉包 = Fruity Soft Clipper 19078) --------------
B=19078
LL=work/batch/$B/p.final.ll
emcc_rc() { ( TMPDIR="$N/tmp" emcc -c "$1" -o "$N/x.o" -w -O0 -msimd128 > "$N/emcc.log" 2>&1 ); echo $?; }
c0=$(emcc_rc "$LL")
python3 - "$LL" "$N/broken.ll" <<'PY'
import sys
s = open(sys.argv[1]).read()
i = s.index('\ndefine ')
j = s.index('\n}\n', i)
body = s[i:j]
k = body.rindex('\n  ret ')
open(sys.argv[2], 'w').write(s[:i] + body[:k] + s[j:])
PY
c1=$(emcc_rc "$N/broken.ll")
echo "NC-E: block $B emcc -c  対照 rc=$c0  ret 除去 rc=$c1  (期待 0 / 非0)"
[ "$c0" = 0 ] && [ "$c1" != 0 ] && chk 'NC-E' ok || chk 'NC-E' ng

R=work/closure/block$(printf %05d $B).ranges.txt
n_all=$(tr ',' '\n' < "$R" | wc -l)
LAST=$(tr ',' '\n' < "$R" | tail -n 1 | cut -d- -f1 | sed 's/^0x//')
d0=$(grep -c '^define' "$LL"); h0=$(grep -c "^define .*@function_$LAST\\b" "$LL")
tr ',' '\n' < "$R" | head -n $((n_all - 1)) | paste -sd, > "$N/ranges_minus1.txt"
bash lift/lift_ranges.sh "$FL_WIN64_DIR/extracted/block$(printf %05d $B)_PE.bin" "$N/ranges_minus1.txt" "$N/lift" p 600 > "$N/lift.log" 2>&1
d1=$(grep -c '^define' "$N/lift/p.final.ll"); h1=$(grep -c "^define .*@function_$LAST\\b" "$N/lift/p.final.ll")
echo "NC-R: block $B ranges $n_all -> $((n_all - 1)), 落とした function_$LAST  対照: define=$d0 present=$h0 / 1 本落とし: define=$d1 present=$h1  (期待 present 1 -> 0, define 減少)"
[ "$h0" = 1 ] && [ "$h1" = 0 ] && [ "$d1" -lt "$d0" ] && [ "$d1" -gt 0 ] && chk 'NC-R' ok || chk 'NC-R' ng

# ---- NC-I: ids_crosscheck ----------------------------------------------------------------
python3 distortion/ids_crosscheck.py --facts "$OUT/facts.json" > "$N/ids_ctrl.out" 2>&1; rc=$?
echo "NC-I 対照 (実測 facts.json): exit=$rc  $(tail -n 1 "$N/ids_ctrl.out")  (期待 0)"
[ "$rc" = 0 ] && chk 'NC-I 対照' ok || chk 'NC-I 対照' ng
python3 - "$OUT/facts.json" "$N/facts_ids.json" <<'PY'
import json, sys
f = json.load(open(sys.argv[1]))
for name, s in f['shells'].items():
    ids = {k: v for k, v in s['host']['ids'].items() if k != 'dyn'}
    if ids:
        k = sorted(ids)[0]
        s['host']['ids'][k] += 1
        print('ID %s の件数 %d -> %d (%s)' % (k, ids[k], ids[k] + 1, name))
        break
json.dump(f, open(sys.argv[2], 'w'))
PY
python3 distortion/ids_crosscheck.py --facts "$N/facts_ids.json" > "$N/ids_bad.out" 2>&1; rc=$?
echo "NC-I ID 件数 +1: exit=$rc  $(tail -n 1 "$N/ids_bad.out")  (期待 1)"
[ "$rc" = 1 ] && chk 'NC-I' ok || chk 'NC-I' ng

# ---- NC-M: matrix_check ----------------------------------------------------------------
python3 distortion/matrix_check.py > "$N/mx_ctrl.out" 2>&1; rc=$?
echo "NC-M 対照: exit=$rc  $(tail -n 1 "$N/mx_ctrl.out")  (期待 0)"
[ "$rc" = 0 ] && chk 'NC-M 対照' ok || chk 'NC-M 対照' ng
python3 - "$OUT/facts.json" "$N/facts_mx.json" <<'PY'
import json, sys
f = json.load(open(sys.argv[1]))
n = next(iter(f['shells']))
f['shells'][n]['closure_funcs'] += 1
json.dump(f, open(sys.argv[2], 'w'))
print('closure_funcs +1 (%s)' % n)
PY
python3 distortion/matrix_check.py --facts "$N/facts_mx.json" > "$N/mx_bad.out" 2>&1; rc=$?
echo "NC-M closure_funcs +1: exit=$rc  $(tail -n 1 "$N/mx_bad.out")  (期待 1)"
[ "$rc" = 1 ] && chk 'NC-M closure' ok || chk 'NC-M closure' ng
mut mx_status 19004 emcc_c_rc 1
python3 distortion/matrix_check.py --status "$N/mx_status.csv" > "$N/mx_bad2.out" 2>&1; rc=$?
echo "NC-M batch (block 19004 の emcc_c_rc <- 1): exit=$rc  $(tail -n 1 "$N/mx_bad2.out")  (期待 1)"
[ "$rc" = 1 ] && chk 'NC-M batch' ok || chk 'NC-M batch' ng

# ---- NC-D: engine_defs の欠落監査 --------------------------------------------------------
ED=$(ls -d $OUT/engine*/ | head -n 1)
mkdir -p "$N/ed"; ln -sf "$PWD/${ED}e.final.ll" "$N/ed/e.final.ll"
cp "${ED}ranges.txt" "$N/ed/ranges.txt"
m0=$(python3 distortion/engine_defs.py "$N/ed" | cut -d, -f1)
printf '%s,0x1000-0x1010' "$(cat "$N/ed/ranges.txt")" > "$N/ed/ranges.txt"
m1=$(python3 distortion/engine_defs.py "$N/ed" | cut -d, -f1)
echo "NC-D: $(basename "$ED") missing_define 対照=$m0  実在しない range を 1 本追加=$m1  (期待 +1)"
[ "$m1" = "$((m0 + 1))" ] && chk 'NC-D' ok || chk 'NC-D' ng

# ---- NC-W: e2e 全体の配線 (--skip-lift 経路で、判定が落ちる status を与えたとき e2e 本体が非 0 で終わり OK 行を出さない) ----
cp "$OUT/status.csv" "$N/backup_status.csv"; cp "$OUT/shell_audit.csv" "$N/backup_audit.csv"
cp work/batch/status.csv "$N/poison_batch.csv"; echo "19004,Fruity Fast Dist,12,8381,0,12,0,0,1,2,1,13" >> "$N/poison_batch.csv"
o=$(BATCH_STATUS="$N/poison_batch.csv" bash distortion/distortion_e2e.sh --skip-lift 2>&1); rc=$?
ok=0; echo "$o" | grep -q '^\[distortion_e2e\] OK' && ok=1
w=0; echo "$o" | grep -q 'FAIL  block 19004.*emcc_c_rc=1' && w=1
cp "$N/backup_status.csv" "$OUT/status.csv"; cp "$N/backup_audit.csv" "$OUT/shell_audit.csv"
echo "NC-W: e2e --skip-lift (BATCH_STATUS の 19004 最終行を emcc_c_rc=1): exit=$rc OK 行=$ok 理由一致=$w  (期待 非0 / 0 / 1)"
[ "$rc" != 0 ] && [ "$ok" = 0 ] && [ "$w" = 1 ] && chk 'NC-W' ok || chk 'NC-W' ng

echo "[distortion_nega] $((total - fail))/$total OK"
[ "$fail" = 0 ] && exit 0
echo "[distortion_nega] FAIL" >&2; exit 1
