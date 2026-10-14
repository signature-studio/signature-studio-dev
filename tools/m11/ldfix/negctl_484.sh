#!/usr/bin/env bash
# negctl_484.sh — audit_lsf.py のネガティブコントロール (#484)。1 件ずつ壊して判定が期待どおり動くことを数値で示す。
#   NC0 無改変 boot_final3.ll                          → 基準 (suspect 8 関数 / 11 site)
#   NC1 5c0270 の 2 つの脱落 store に load を足す       → 5c0270 が消える (7 関数 / 9 site)
#   NC2 409c80 の F3c 修復 store (%ldfxc159) を %arg1 に戻す → 409c80 の w64 が増える (8 関数 / 12 site)
#   NC3 image の 5c0270 区間を nop で潰す (機械語側を壊す)    → 5c0270 が消える (IR だけでは判定しない)
#   NC4 IR 側を無害化: 5c0270 の 2 store を `store i64 0` にする → 5c0270 が消える (機械語だけでは判定しない)
# 使い方: bash tools/m11/ldfix/negctl_484.sh        (環境: M11_WORK=…/tools/m11/work, PY=capstone 入りの python)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
W="${M11_WORK:-$REPO/tools/m11/work}"
PY="${PY:-python3}"
T="${RUNNER_TEMP:-/tmp}/negctl_484"; mkdir -p "$T"
CFG="$W/boot*.drc.config.json"
IR="$W/boot_final3.ll"
IMG="$W/m11_image.bin"
run() { "$PY" "$HERE/audit_lsf.py" "$1" "${2:-$IMG}" "$CFG" --no-disp --json "$T/$3.json" 2>&1 | tail -2 | head -1; }
vas() { "$PY" -c "import json,sys; d=json.load(open(sys.argv[1]))['suspects']; print(' '.join(sorted(d, key=lambda x:int(x,16))))" "$T/$1.json"; }

echo "[NC0] 無改変"; run "$IR" "$IMG" nc0; echo "  suspects: $(vas nc0)"

echo "[NC1] 5c0270 の脱落 store 2 件を load 経由に修復した IR"
"$PY" - "$IR" "$T/nc1.ll" <<'EOF'
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
b2 = re.sub(r'^(\s*)store i64 %arg2, ptr (%[\w.$-]+, align 8)$', fix, b, flags=re.M)
assert n[0] == 2, n
open(sys.argv[2], 'w').write(t[:m.start()] + b2 + t[e:])
print('  patched stores:', n[0])
EOF
run "$T/nc1.ll" "$IMG" nc1; echo "  suspects: $(vas nc1)"

echo "[NC2] 409c80 の F3c 修復 store を %arg1 (ポインタ自身) に戻した IR"
"$PY" - "$IR" "$T/nc2.ll" <<'EOF'
import re, sys
t = open(sys.argv[1], errors='replace').read()
m = re.search(r'^define [^@]*@function_409c80\(', t, re.M); e = t.index('\n}', m.end())
b = t[m.start():e]
b2, n = re.subn(r'^(\s*)store i64 %ldfxc\d+, ptr (%[\w.$-]+, align 8)$', r'\1store i64 %arg1, ptr \2', b, flags=re.M)
assert n == 1, n
open(sys.argv[2], 'w').write(t[:m.start()] + b2 + t[e:])
print('  reverted stores:', n)
EOF
run "$T/nc2.ll" "$IMG" nc2; echo "  suspects: $(vas nc2)"; "$PY" -c "
import json; d=json.load(open('$T/nc2.json'))['suspects']['409c80']; print('  409c80 entries:', [(x['arg'],x['width'],x['excess']) for x in d])"

echo "[NC3] image の 5c0270 区間 (5c0270..5c0392) を nop に潰した機械語"
"$PY" - "$IMG" "$T/nc3.bin" <<'EOF'
import sys
d = bytearray(open(sys.argv[1], 'rb').read())
lo, hi = 0x5c0270 - 0x400000, 0x5c0393 - 0x400000
d[lo:hi] = b'\x90' * (hi - lo)
open(sys.argv[2], 'wb').write(d)
EOF
run "$IR" "$T/nc3.bin" nc3; echo "  suspects: $(vas nc3)"

echo "[NC4] IR 側のみ無害化 (5c0270 の arg2 store を定数 store に)"
"$PY" - "$IR" "$T/nc4.ll" <<'EOF'
import re, sys
t = open(sys.argv[1], errors='replace').read()
m = re.search(r'^define [^@]*@function_5c0270\(', t, re.M); e = t.index('\n}', m.end())
b2, n = re.subn(r'^(\s*)store i64 %arg2, ptr (%[\w.$-]+, align 8)$', r'\1store i64 0, ptr \2', t[m.start():e], flags=re.M)
assert n == 2, n
open(sys.argv[2], 'w').write(t[:m.start()] + b2 + t[e:])
EOF
run "$T/nc4.ll" "$IMG" nc4; echo "  suspects: $(vas nc4)"
