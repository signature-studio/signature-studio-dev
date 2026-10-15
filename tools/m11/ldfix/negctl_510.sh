#!/usr/bin/env bash
# negctl_510.sh — audit_lsf_ssa.py のネガティブコントロール (#510)。1 件ずつ壊して/直して判定が期待どおり動くことを数値で示す。
#   NC0 無改変 boot_final3.ll                                  → 基準
#   NC1 5c0270 の脱落 store 2 本に load を足す (IR 修復)        → 5c0270 の SUSPECT が 2 減り、alg1 の対象関数が 1 減る
#   NC2 100be60 (alg2 では OK の関数) の load 由来の store 値を `trunc %arg2` に差し替える (IR 破壊) → unk/store が OK→SUSPECT に 1 動き、alg1 対象関数が 1 増える
#   NC3 image の 5c0270 区間を nop に潰す (機械語側を壊す)       → 5c0270 の site (lsf 2 + frame 1) が列挙から消える
#   NC4 ablation: --no-alloca-prop                              → reg2mem alloca 経由の由来伝播を切ると偽陽性候補が増える (設計の必要性)
#   NC5 525600 (CELL_COLLAPSED) の IR を 2 段 load に修復          → 525622 が alg3 OK / CELL_DEEP に動き、CELL_COLLAPSED が 1 減る
#   NC6 525600 の IR をセル内容 V (image の実データ) 直読みに変える  → 525622 が FOLDED_OK に動き、CELL_COLLAPSED が 1 減る (RetDec の静的解決は脱落でない)
#   NC7 52a750 (CELL_DEEP) の 2 段 load をセル自身の 1 段 load に壊す → 52a7a8 が alg3 SHALLOW / CELL_COLLAPSED に動く
# 使い方: bash tools/m11/ldfix/negctl_510.sh        (環境: M11_WORK=…/tools/m11/work, PY=capstone 入りの python)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
W="${M11_WORK:-$REPO/tools/m11/work}"
PY="${PY:-python3}"
T="${RUNNER_TEMP:-/tmp}/negctl_510"; mkdir -p "$T"
CFG="$W/boot*.drc.config.json"; IR="$W/boot_final3.ll"; IMG="$W/m11_image.bin"
run() { "$PY" "$HERE/audit_lsf_ssa.py" "$1" "${2:-$IMG}" "$CFG" --json "$T/$3.json" "${@:4}" | tail -1; }
sus() { "$PY" -c "
import json,sys; d=json.load(open(sys.argv[1])); f=d['functions'].get(sys.argv[2])
if f is None: print('  %s: (site 無し = 列挙から消えた)' % sys.argv[2]); sys.exit()
print('  %s: alg2=%s alg1_deficit=%s' % (sys.argv[2], [(s['addr'],s['alg2']) for s in f['sites'] if not s['frame']], [(x['w'],x['deficit']) for x in f['alg1']]))" "$T/$1.json" "$2"; }
fns() { "$PY" -c "
import json,sys,collections; d=json.load(open(sys.argv[1]))
c=collections.Counter(s['cell']['verdict'] for r in d['functions'].values() for s in r['sites'] if s.get('cell'))
print('  alg1_fns=%d alg2_fns=%d alg3_fns=%d (alg1|alg2)=%d cell=%s' % (len(d['alg1_fns']), len(d['alg2_fns']), len(d['alg3_fns']), len(set(d['alg1_fns'])|set(d['alg2_fns'])), dict(sorted(c.items()))))" "$T/$1.json"; }
cellsite() { "$PY" -c "
import json,sys; d=json.load(open(sys.argv[1])); f=d['functions'].get(sys.argv[2])
print('  %s: %s' % (sys.argv[2], [(s['addr'], 'alg3=' + s['alg3'], (s.get('cell') or {}).get('verdict')) for s in f['sites'] if not s['frame']]))" "$T/$1.json" "$2"; }

echo "[NC0] 無改変"; run "$IR" "$IMG" nc0; fns nc0; sus nc0 5c0270; sus nc0 100be60; cellsite nc0 525600; cellsite nc0 52a750

echo "[NC1] 5c0270 の脱落 store 2 件を load 経由に修復した IR"
"$PY" - "$IR" "$T/nc1.ll" <<'PYEOF'
import re, sys
t = open(sys.argv[1], errors='replace').read()
m = re.search(r'^define [^@]*@function_5c0270\(', t, re.M); e = t.index('\n}', m.end())
b = t[m.start():e]
n = [0]
def fix(mm):
    n[0] += 1
    k = n[0]
    return ('%s%%nc1_p%d = inttoptr i64 %%arg2 to ptr\n%s%%nc1_v%d = load i64, ptr %%nc1_p%d, align 8\n%sstore i64 %%nc1_v%d, ptr %s'
            % (mm.group(1), k, mm.group(1), k, k, mm.group(1), k, mm.group(2)))
# ldfix F3c (#509) は同じ修復を現 IR に入れているため、脱落形に戻してから patch する (戻さないと assert で止まり nc1.json が出ない)
b, rv = re.subn(r'^(\s*)%(ldfxn\d+)_p = inttoptr i64 %arg2 to ptr\n\s*%\2 = load i64, ptr %\2_p, align 8\n\s*store i64 %\2, (ptr %[\w.$-]+, align 8)$',
                r'\1store i64 %arg2, \3', b, flags=re.M)
print('  ldfix 済みの store を脱落形に戻した数:', rv)
b2 = re.sub(r'^(\s*)store i64 %arg2, ptr (%[\w.$-]+, align 8)$', fix, b, flags=re.M)
assert n[0] == 2, n
open(sys.argv[2], 'w').write(t[:m.start()] + b2 + t[e:])
print('  patched stores:', n[0])
PYEOF
run "$T/nc1.ll" "$IMG" nc1; fns nc1; sus nc1 5c0270

echo "[NC2] 100be60 の load 由来 store (store i32 %0, ptr %3) を trunc %arg2 に差し替えた IR"
"$PY" - "$IR" "$T/nc2.ll" <<'PYEOF'
import re, sys
t = open(sys.argv[1], errors='replace').read()
m = re.search(r'^define [^@]*@function_100be60\(', t, re.M); e = t.index('\n}', m.end())
b = t[m.start():e]
b2, n = re.subn(r'^(\s*)store i32 %0, ptr %3, align 4$', r'\1%nc2 = trunc i64 %arg2 to i32\n\1store i32 %nc2, ptr %3, align 4', b, flags=re.M)
assert n == 1, n
open(sys.argv[2], 'w').write(t[:m.start()] + b2 + t[e:])
print('  patched stores:', n)
PYEOF
run "$T/nc2.ll" "$IMG" nc2; fns nc2; sus nc2 100be60

echo "[NC3] image の 5c0270 区間 (5c0270..5c0392) を nop に潰した機械語"
"$PY" - "$IMG" "$T/nc3.bin" <<'PYEOF'
import sys
d = bytearray(open(sys.argv[1], 'rb').read())
lo, hi = 0x5c0270 - 0x400000, 0x5c0393 - 0x400000
d[lo:hi] = b'\x90' * (hi - lo)
open(sys.argv[2], 'wb').write(d)
PYEOF
run "$IR" "$T/nc3.bin" nc3; fns nc3; sus nc3 5c0270

echo "[NC4] ablation: --no-alloca-prop (reg2mem alloca 経由の由来伝播を切る)"
run "$IR" "$IMG" nc4 --no-alloca-prop; fns nc4

echo "[NC5] 525600 の cell 1 段 load を 2 段 load (cell -> 実変数) に修復した IR"
"$PY" - "$IR" "$T/nc5.ll" <<'PYEOF'
import re, sys
t = open(sys.argv[1], errors='replace').read()
m = re.search(r'^define [^@]*@function_525600\(', t, re.M); e = t.index('\n}', m.end())
b = t[m.start():e]
b2, n = re.subn(r'^(\s*)%8 = load i32, ptr inttoptr \(i64 18761216 to ptr\), align 8$',
                r'\1%nc5p = load i64, ptr inttoptr (i64 18761216 to ptr), align 8\n\1%nc5q = inttoptr i64 %nc5p to ptr\n\1%8 = load i32, ptr %nc5q, align 4', b, flags=re.M)
assert n == 1, n
open(sys.argv[2], 'w').write(t[:m.start()] + b2 + t[e:])
PYEOF
run "$T/nc5.ll" "$IMG" nc5; fns nc5; cellsite nc5 525600

echo "[NC6] 525600 の load をセル内容 V (image 実データ 0x11e60b4 = 18768052) 直読みにした IR (RetDec の静的解決を模擬)"
"$PY" - "$IR" "$T/nc6.ll" <<'PYEOF'
import re, sys
t = open(sys.argv[1], errors='replace').read()
m = re.search(r'^define [^@]*@function_525600\(', t, re.M); e = t.index('\n}', m.end())
b = t[m.start():e]
b2, n = re.subn(r'%8 = load i32, ptr inttoptr \(i64 18761216 to ptr\)', '%8 = load i32, ptr inttoptr (i64 18768052 to ptr)', b)
assert n == 1, n
open(sys.argv[2], 'w').write(t[:m.start()] + b2 + t[e:])
PYEOF
run "$T/nc6.ll" "$IMG" nc6; fns nc6; cellsite nc6 525600

echo "[NC7] 52a750 (CELL_DEEP) の 2 段 load (%3 = load i64, ptr %2) をセル自身 (18818816) の 1 段 load に壊した IR"
"$PY" - "$IR" "$T/nc7.ll" <<'PYEOF'
import re, sys
t = open(sys.argv[1], errors='replace').read()
m = re.search(r'^define [^@]*@function_52a750\(', t, re.M); e = t.index('\n}', m.end())
b = t[m.start():e]
b2, n = re.subn(r'^(\s*)%3 = load i64, ptr %2, align 8$', r'\1%3 = load i64, ptr inttoptr (i64 18818816 to ptr), align 8', b, flags=re.M)
assert n == 1, n
open(sys.argv[2], 'w').write(t[:m.start()] + b2 + t[e:])
PYEOF
run "$T/nc7.ll" "$IMG" nc7; fns nc7; cellsite nc7 52a750

miss=0
for k in nc0 nc1 nc2 nc3 nc4 nc5 nc6 nc7; do [ -s "$T/$k.json" ] || { echo "[negctl_510] MISSING: $k.json (評価されていない)"; miss=1; }; done
exit $miss
