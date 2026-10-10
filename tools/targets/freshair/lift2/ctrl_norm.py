#!/usr/bin/env python3
"""ctrl_norm.py <scen.txt> <native.txt> <wasm.txt> [<fma>] — FA-2c 制御層の bit-exact 判定。

ダンプには **ポインタ値** が含まれる (native = host heap/stack アドレス / wasm = guest アドレス)。
ポインタ値そのものは環境依存なので、両側に **同一規則** でマスクしてから比較する:
  8 byte アラインごとに値 >= MASK_MIN (4GB) なら定数に置換 (両側同時 → data が巻き込まれても公平)。
更に、scen.txt のシナリオ数と行数の一致・ERR 有無も検査する (空 PASS 防止)。
"""
import sys, struct

MASK_MIN = 0x100000000
MASK_TO = 0x00000000feedface

def _mask_pos(tok):
    """16 進トークン内の **任意位置** の 16 桁 (qword) をスライド検査し、値 >= MASK_MIN の位置を True に。"""
    pos = [False] * len(tok)
    for k in range(0, len(tok) - 15):
        w = tok[k:k + 16]
        if not all(c in '0123456789abcdef' for c in w):
            continue
        if int(w, 16) >= MASK_MIN:
            for j in range(k, k + 16):
                pos[j] = True
    return pos

def norm_pair(x, y):
    """両側のマスク位置の **和集合** でマスクする (ポインタ値の大きさが環境で異なり境界がずれるため)。
    長さが不一致のトークンはそのまま (別の差分として検出される)。"""
    if len(x) != len(y):
        return x, y
    px, py = _mask_pos(x), _mask_pos(y)
    m = [a or b for a, b in zip(px, py)]
    return (''.join('m' if m[i] else x[i] for i in range(len(x))),
            ''.join('m' if m[i] else y[i] for i in range(len(y))))

scen, nat, was = sys.argv[1], sys.argv[2], sys.argv[3]
fma = sys.argv[4] if len(sys.argv) > 4 else '?'
nscen = sum(1 for l in open(scen) if l.strip())
A = [l.rstrip('\n') for l in open(nat)]
B = [l.rstrip('\n') for l in open(was)]
A = [a for a in A if a]; B = [b for b in B if b]
era = sum(1 for a in A if '|ERR' in a); erb = sum(1 for b in B if '|ERR' in b)
# ERR は「実機機械語でも同じ scenario が落ちる」ことを許容するが、**両側で同一 scenario** であることを要求する
ea = set(a.split(' ', 1)[0] for a in A if '|ERR' in a)
eb = set(b.split(' ', 1)[0] for b in B if '|ERR' in b)
err_sets_equal = (ea == eb)
norm_a = []; norm_b = []
for a, b in zip(A, B):
    ta, tb = [], []
    for x, y in zip(a.split(' '), b.split(' ')):
        x, y = norm_pair(x, y)
        ta.append(x); tb.append(y)
    norm_a.append(' '.join(ta)); norm_b.append(' '.join(tb))
mismatch = sum(1 for x, y in zip(norm_a, norm_b) if x != y)
print('fma=%s: scenarios %d, lines native/wasm %d/%d, mismatch %d (pointer-masked), ERR native/wasm %d/%d (同一 scenario: %s)'
      % (fma, nscen, len(A), len(B), mismatch, era, erb, 'yes' if err_sets_equal else 'NO'))
ok = (len(A) == nscen and len(B) == nscen and mismatch == 0 and err_sets_equal)
if not ok:
    for x, y in zip(norm_a, norm_b):
        if x != y:
            k = 0
            while k < min(len(x), len(y)) and x[k] == y[k]:
                k += 1
            print('  first mismatch at char %d:\n    n: %s\n    w: %s' % (k, x[max(0, k-24):k+48], y[max(0, k-24):k+48]))
            break
sys.exit(0 if ok else 1)
