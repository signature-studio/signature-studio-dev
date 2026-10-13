#!/usr/bin/env bash
# PLG-F2 (#199) ネガティブコントロール: f2_step1.sh の各検査が「壊れた入力」で FAIL (非 0 / 不一致) になることを確認する。
#   bash tools/plugins/f2/nc_f2.sh      (前提: f2_step1.sh 実行済み = work/batch/*, work/closure/*, work/f2/*)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
source "$ROOT/../shared/env.sh"
[ -f "$HERE/env.sh" ] && source "$HERE/env.sh"
cd "$ROOT"
N=work/f2/nc; rm -rf "$N"; mkdir -p "$N"
B=18984; PE="$FL_WIN64_DIR/extracted/block$(printf %05d $B)_PE.bin"
# NC1: 閉包 ranges を 1 本欠かして lift → define 数が closure JSON の unique_funcs と不一致 (closure_stats.py の assert が FAIL する条件)
RG="work/closure/block$(printf %05d $B).ranges.txt"
tr ',' '\n' < "$RG" | grep . | sed '$d' | paste -sd, > "$N/ranges_minus1.txt"
bash lift/lift_ranges.sh "$PE" "$N/ranges_minus1.txt" "$N/nc1" p 600 > "$N/nc1.log" 2>&1
D=$(grep -c '^define' "$N/nc1/p.final.ll"); C=$(python3 -c "import json;print(json.load(open('work/closure/block$(printf %05d $B).json'))['unique_funcs'])")
echo "NC1 ranges-1 lift: defines=$D closure=$C -> $([ "$D" != "$C" ] && echo 'DETECTED (不一致)' || echo 'NOT DETECTED')"
# NC2: 正常 IR に不正行を足すと emcc -c が非 0 (batch_lift の emcc_c_rc 列が識別力を持つ)
cp "work/batch/$B/p.final.ll" "$N/bad.ll"; echo "  %zz = bogus i64 undefined_op" >> "$N/bad.ll"
( source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; TMPDIR="$N" emcc -c "$N/bad.ll" -o "$N/bad.o" -w -O0 -msimd128 > "$N/bad.emcc.log" 2>&1 ); rc=$?
( source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; TMPDIR="$N" emcc -c "work/batch/$B/p.final.ll" -o "$N/ok.o" -w -O0 -msimd128 > "$N/ok.emcc.log" 2>&1 ); rc0=$?
echo "NC2 emcc -c: 正常 IR rc=$rc0 / 不正行追加 IR rc=$rc -> $([ "$rc0" = 0 ] && [ "$rc" != 0 ] && echo 'DETECTED' || echo 'NOT DETECTED')"
# NC3: 間接 call 監査の識別力 — Parametric EQ (19058) の Eff_Render (function_6d0350) に間接 call を 1 本注入した IR で ir_call_ind が 0→1 になる
cp work/batch/19058/p.final.ll "$N/inj.ll"
python3 - "$N/inj.ll" <<'PY'
import sys, re
p = sys.argv[1]; s = open(p).read()
k = 'define i64 @function_6d0350(i64 %arg1, i64 %arg2, i64 %arg3, i64 %arg4) local_unnamed_addr {\ndec_label_pc_6d0350:\n'
assert k in s
s = s.replace(k, k + '  %inj.p = inttoptr i64 %arg2 to ptr\n  %inj.c = call i64 %inj.p(i64 %arg1)\n')
open(p, 'w').write(s)
PY
python3 ../icall/audit_icall.py --pe "$FL_WIN64_DIR/extracted/block19058_PE.bin" --ir "$N/inj.ll" --funcs work/f2/19058.funcs --json "$N/inj.icall.json" --label inj > /dev/null
python3 - "$N/inj.icall.json" <<'PY'
import json, sys
j = json.load(open(sys.argv[1]))
b = json.load(open('work/f2/19058.icall.json'))
r = {x['fn']: x for x in j['per_fn_cmp']}['0x6d0350']
print('NC3 audit: 元 IR ir_call_ind_total=%d / 注入 IR=%d (0x6d0350 の ir_call_ind=%d) -> %s' % (
    b['ir_call_ind_total'], j['ir_call_ind_total'], r['ir_call_ind'],
    'DETECTED' if j['ir_call_ind_total'] == b['ir_call_ind_total'] + 1 and r['ir_call_ind'] == 1 else 'NOT DETECTED'))
PY
