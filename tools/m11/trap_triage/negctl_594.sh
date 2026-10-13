#!/usr/bin/env bash
# #594 再現 + ネガコン + gate: 8cc190 系 OOB (unit 56, 58-63) の原因 = 417b70 の `Q(a)` が上位 4B 未初期化 (D17 型) を, 設定を 1 つずつ差し替えて実測する.
#   usage: negctl_594.sh      前提: work/ に m11 素材 (work-m11) と PE (FL_WIN64_DIR) 無しでも可 (build は work/boot_final*.ll から)
#   構成 (m11_ov.c を python で加工して work/obj/ov.o に差し替え → m11_build.sh → survey_units.mjs):
#     base      現行 m11_ov.c (無加工)                         : 基準. 8cc190 系 OOB の unit 集合を数える
#     base2     同上 (2 回目)                                   : 決定性 (base と unit 単位で kind 完全一致)
#     probe     8cc190 に M11_TRACE probe (self/cmp/cnt/cap)    : 辞書 [g+0x410] の中身が正常であること (入力不正でない)
#     mask      417b70 の `Q(a)` を下位 4B に mask (実験)       : 58-63 が oob→ok, ok 退行 0
#     maskneg   mask の ネガコン (mask 値 = 全 bit 1 = 無加工と同義) : base と kind 完全一致, 58-63 は oob のまま
#     fill00 / fillff   base + SV_STK_FILL=00 / ff (各 unit 直前に SP 直下 8 KiB を埋める): 残骸感度. 00 で 58-63 が ok, ff で oob のまま
#   gate: 条件を満たさなければ exit 1 (FAIL を出して続行しない).  終了時に work/obj/ov.o を現行 m11_ov.c から再生成する.
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -I."
OUT=work/negctl_594; mkdir -p "$OUT"
[ -f work/obj/boot.o ] || bash m11_build.sh > /dev/null
restore() { rm -f work/ov_ablate.c; touch m11_ov.c; bash m11_build.sh > /dev/null 2>&1; echo "ov.o を現行 m11_ov.c から再生成した"; }
trap restore EXIT

gen() { # gen <構成> → work/ov_ablate.c
  python3 - "$1" <<'PY'
import sys
c = sys.argv[1]
s = open('m11_ov.c').read()
def rep(old, new):
    global s
    assert s.count(old) == 1, 'anchor not unique: ' + old
    s = s.replace(old, new)
if c in ('base', 'base2'):
    pass
elif c == 'probe':
    rep('u64 function_8cc190(u64 self, u64 key, u64 val) {\n',
        'u64 function_8cc190(u64 self, u64 key, u64 val) {\n'
        '    M11_TRACE("[p8cc190] self=%llx key=%llx cnt=%llx cap=%llx items=%llx cmp=%llx\\n", self, key, Q(self+0x10), Q(self+0x20), Q(self+8), Q(self+0x18));\n')
elif c in ('mask', 'maskneg'):
    m = '0xffffffffull' if c == 'mask' else '0xffffffffffffffffull'
    rep('    u64 p = Q(a);\n    u64 len = Q(lengths);\n    if ((long long)len <= 0) {',
        '    u64 p = Q(a) & %s;   /* #594 EXPERIMENT */\n    u64 len = Q(lengths);\n    if ((long long)len <= 0) {' % m)
elif c in ('fill00', 'fillff'):
    pass
else:
    sys.exit('unknown config ' + c)
open('work/ov_ablate.c', 'w').write(s)
PY
}
run() { # run <構成> <env...>
  local c="$1"; shift
  gen "$c" || exit 1
  emcc -c work/ov_ablate.c -o work/obj/ov.o $CF || { echo "FAIL: $c ov compile"; exit 1; }
  touch work/obj/ov.o
  bash m11_build.sh > work/negctl_build.log 2>&1 || { echo "FAIL: $c link"; tail -3 work/negctl_build.log; exit 1; }
  local s e; s=$(date +%s.%N)
  env SV_TRACE_AT=99999 "$@" node trap_triage/survey_units.mjs "$OUT/$c.json" > "$OUT/$c.out" 2> "$OUT/$c.err"
  e=$(date +%s.%N)
  printf '%-8s %5.1fs  %s  load=%s\n' "$c" "$(echo "$e - $s" | bc)" "$(grep -a SURVEY_UNITS "$OUT/$c.out" | head -1)" "$(cut -d' ' -f1 /proc/loadavg)"
}
run base NONE=1
run base2 NONE=1
run probe NONE=1
run mask NONE=1
run maskneg NONE=1
# fill00 / fillff は base のビルド (無加工 ov.o) で SV_STK_FILL だけ変える
gen base; emcc -c work/ov_ablate.c -o work/obj/ov.o $CF && touch work/obj/ov.o && bash m11_build.sh > work/negctl_build.log 2>&1 || { echo "FAIL: base relink"; exit 1; }
for f in 00 ff; do
  s=$(date +%s.%N)
  SV_TRACE_AT=99999 SV_STK_FILL=$f node trap_triage/survey_units.mjs "$OUT/fill$f.json" > "$OUT/fill$f.out" 2> "$OUT/fill$f.err"
  e=$(date +%s.%N)
  printf '%-8s %5.1fs  %s  load=%s\n' "fill$f" "$(echo "$e - $s" | bc)" "$(grep -a SURVEY_UNITS "$OUT/fill$f.out" | head -1)" "$(cut -d' ' -f1 /proc/loadavg)"
done

python3 - "$OUT" <<'PY'
import json, sys, re, collections
O = sys.argv[1]
def load(n): return {r['unit']: r for r in json.load(open('%s/%s.json' % (O, n)))}
kinds = lambda d: {u: r['kind'] for u, r in d.items()}
base, base2, mask, maskneg, f00, fff = (load(n) for n in ('base', 'base2', 'mask', 'maskneg', 'fill00', 'fillff'))
fails = []
def gate(name, ok, detail):
    print('%s %-52s %s' % ('PASS' if ok else 'FAIL', name, detail))
    if not ok: fails.append(name)
# 8cc190 系 OOB = 最上位 frame を問わず frames に function_8cc190 と function_8c7a10 を含む oob unit
def fam(d): return sorted(u for u, r in d.items() if r['kind'] == 'oob' and 'function_8cc190' in r.get('frames', []) and 'function_8c7a10' in r.get('frames', []))
F = fam(base)
gate('G1 base の 8cc190←8c7a10 系 OOB = [56,58..63]', F == [56] + list(range(58, 64)), 'n=%d %s' % (len(F), F))
gate('G2 決定性: base と base2 の kind 完全一致', kinds(base) == kinds(base2), 'diff=%d' % sum(1 for u in base if base[u]['kind'] != base2[u]['kind']))
# probe: 全 Add 呼出しで self / cmp (FComparer) が 1 種類, cnt==cap==0x40 の Grow を観測
ps = [re.match(r'\[p8cc190\] self=(\w+) key=(\w+) cnt=(\w+) cap=(\w+) items=(\w+) cmp=(\w+)', l) for l in open(O + '/probe.err', errors='replace')]
ps = [m.groups() for m in ps if m]
selfs = {p[0] for p in ps}; cmps = {p[5] for p in ps}; grow = [p for p in ps if p[2] == p[3]]
gate('G3 probe: 辞書 self/FComparer が 1 種で Add 呼出しが 64 回以上', len(selfs) == 1 and len(cmps) == 1 and len(ps) >= 64, 'Add=%d self=%s cmp=%s' % (len(ps), selfs, cmps))
gate('G4 probe: cnt==cap==0x40 の Grow 呼出しがある (OOB の入口)', any(p[2] == '40' for p in grow), 'Grow(cnt==cap) caps=%s' % sorted({p[3] for p in grow}))
chg = sorted(u for u in base if base[u]['kind'] == 'oob' and mask[u]['kind'] == 'ok')
gate('G5 mask: 58..63 が oob→ok', chg and all(u in chg for u in range(58, 64)), 'oob→ok=%s' % chg)
reg = sorted(u for u in base if base[u]['kind'] == 'ok' and mask[u]['kind'] != 'ok')
gate('G6 mask: ok 退行 0', not reg, 'ok 退行=%s' % reg)
gate('G7 ネガコン maskneg(全 bit mask) = base と kind 完全一致', kinds(maskneg) == kinds(base), 'diff=%d' % sum(1 for u in base if base[u]['kind'] != maskneg[u]['kind']))
gate('G8 ネガコン maskneg で 58..63 は oob のまま', all(maskneg[u]['kind'] == 'oob' for u in range(58, 64)), [maskneg[u]['kind'] for u in range(58, 64)])
gate('G9 fill00: 58..63 が ok (残骸 0 埋めで消える)', all(f00[u]['kind'] == 'ok' for u in range(58, 64)), [f00[u]['kind'] for u in range(58, 64)])
gate('G10 fillff: 58..63 は oob のまま', all(fff[u]['kind'] == 'oob' for u in range(58, 64)), [fff[u]['kind'] for u in range(58, 64)])
print('SUMMARY %s' % ('FAIL: ' + ', '.join(fails) if fails else 'ALL PASS'))
sys.exit(1 if fails else 0)
PY
rc=$?
exit $rc
