#!/usr/bin/env python3
"""ir_kh_p1.py — kHs 向け [P1] comis/ucomis flag 修復 (m6/ir6_pass.py [P1] の PoC 再実装)。

RetDec は ucomisd/comiss の CF/ZF/PF を直前の無関係な cmp 由来 SSA (例: %cf.0 = icmp eq i8 <this+0x78>, 0)
に誤結線する (gain::GainDsp::process で実測: jae が first-flag byte に依存する silent miscompile)。
  call void @__asm_[v]ucomis{s,d}(i128 %A, <i128 %B | i64/i32 const bits>)
の直後 (同一 basic block 8 行以内) で参照される %cf.N / %zf.N / %pf.N を、fcmp 由来の新 SSA に差し替える。
  CF = ult(A,B) (unordered 含む) / ZF = ueq(A,B) / PF = uno(A,B)
usage: ir_kh_p1.py in.ll out.ll
"""
import os
import re
import sys

CALL = re.compile(r"^(\s*)call void @__asm_(v)?(u)?comis(s|d)(?:__\d+|\.\d+)?\((i128) (%[\w.\-]+), (i128 %[\w.\-]+|i64 -?\d+|i32 -?\d+)\)")
FLAG = re.compile(r"%(cf|zf|pf)\.\d+\b")


def main(src, dst):
    L = open(src).read().split('\n')
    out, n_site, n_rep = [], 0, 0
    i = 0
    while i < len(L):
        l = L[i]
        out.append(l)
        m = None if os.environ.get('KH_P1_NOFIX') else CALL.match(l)
        if m:
            n_site += 1
            kind = m.group(4)
            ty, ity = ('double', 'i64') if kind == 'd' else ('float', 'i32')
            a, b = m.group(6), m.group(7)
            t = 'kp%d' % i
            ins = [f"  %{t}.a1 = trunc i128 {a} to {ity}", f"  %{t}.f1 = bitcast {ity} %{t}.a1 to {ty}"]
            if b.startswith('i128'):
                ins += [f"  %{t}.a2 = trunc {b} to {ity}", f"  %{t}.f2 = bitcast {ity} %{t}.a2 to {ty}"]
            else:
                ins += [f"  %{t}.f2 = bitcast {b} to {ty}"]
            ins += [f"  %{t}.lt = fcmp ult {ty} %{t}.f1, %{t}.f2", f"  %{t}.eq = fcmp ueq {ty} %{t}.f1, %{t}.f2",
                    f"  %{t}.un = fcmp uno {ty} %{t}.f1, %{t}.f2"]
            out.extend(ins)
            names = {'cf': f"%{t}.lt", 'zf': f"%{t}.eq", 'pf': f"%{t}.un"}
            j = i + 1
            while j < min(i + 9, len(L)) and not re.match(r"^[\w.\-]+:", L[j]):
                def rep(mm):
                    return names[mm.group(1)]
                nl, k = FLAG.subn(rep, L[j])
                if k:
                    n_rep += k
                    L[j] = nl
                j += 1
        i += 1
    seen, ded, ndup = set(), [], 0
    for l in out:
        m = re.match(r"^declare \S+ @([\w.\-]+)\(", l)
        if m:
            if m.group(1) in seen:
                ndup += 1
                continue
            seen.add(m.group(1))
        ded.append(l)
    open(dst, 'w').write('\n'.join(ded))
    print(f"[kh_p1] comis sites {n_site}, flag refs rewritten {n_rep}, duplicate declare removed {ndup}")


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
