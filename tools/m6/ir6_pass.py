#!/usr/bin/env python3
# M6 #5: IR pass [P1] comiss/UCOMISS/comisd/UCOMISD/vcomisd 系 flag (CF/ZF/PF) 紐付け修復.
#   修復形 (RetDec IR における) 'br i1 %<cf/zf>.00reload' の flag 変から新定義 SSA に置き換え:
#     sc_Call comis (i128 %A, i128 %B):
#       %flag.b.fs1  = trunc i128 %A to f64-widths (i64 for comisd, i32 for comiss)
#       %flag.b.f64  = bitcast f64 %flag.b.fs1 to double
#       [同様に %flag.b.fs2 の]
#       %flag.b.lt   = fcmp ult double %f1, %f2
#       %flag.b.eq   = fcmp ueq double %f1, %f2
#       %flag.b.uord = fcmp uno double %f1, %f2
#       %flag.cf     = or i1 %flag.lt, %flag.uord
#       %flag.zf     = or i1 %flag.eq, %flag.uord
#       %flag.pf     = %flag.uord
#     br i1 %cf.<n>.reload → br i1 %flag.cf
# 対応形式:
#   (a) 'br i1 %cf.0.reload, label X, label Y' (jbe/jb 由来; RetDec は comis flag 
#       の side-effect を無いとき XX.reload 変から抜けていた)
#   (b) '%N = or i1 %cf.<n>.reload, %zf.<n>.reload' (jbe/jbe-log 組合せの SSA) →
#       同様に置き換え (この SSA 群を置き換える場合は, 変数名-番号が共有で使用される)
# parec: 診断に (a) の hit 率と (b) の hit 率を出す
import sys, re
from collections import Counter


COMIS_RE = re.compile(
    r"^(\s*)call void @__asm_(v)?(u)?(comis)(s|d)(?:__(\d+))?\(({?[^)]*})\)(,?.*)$")
ARG2_RE = re.compile(r"i128 (%[\w.\-]+), (i128 %[\w.\-]+|i64 (?:%[\w.\-]+|-?\d+))")


def parse_call(l):
    m = re.match(r"^(\s*)call void @__asm_(v)?(u)?(comis)(s|d)(?:__(\d+))?\((.*?)\)(,?.*)$", l)
    if not m:
        return None
    mm = ARG2_RE.match(m.group(7))
    if not mm:
        return None
    a1 = mm.group(1)
    a2raw = mm.group(2)
    a2 = a2raw[len('i128 '):] if a2raw.startswith('i128') else a2raw[len('i64 '):]
    a2_is_i128 = a2raw.startswith('i128')
    a2_is_const = re.fullmatch(r'-?\d+', a2) is not None
    return (m.keras if False else None,
            m.group(2), m.group(4), a1, a2, a2_is_i128, a2_is_const)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    lines = open(src).read().split('\n')
    sites = [i for i, l in enumerate(lines) if 'void @__asm_' in l and 'comis' in l]
    print('[P1] comis sites:', len(sites))
    inserts = {}
    hits = Counter()
    for idx in sites:
        pc = parse_call(lines[idx])
        if pc is None:
            continue
        (mk, iss, kind, a1, a2, a2_is_i128, a2_is_const) = pc
        ty = 'double' if kind == 'd' else 'float'
        opx = []
        tag = 'pc%d' % idx
        opx.append(f"  %{tag}fs1 = trunc i128 {a1} to {'i64' if kind=='d' else 'i32'}")
        opx.append(f"  %{tag}f1 = bitcast {'i64' if kind=='d' else 'i32'} %{tag}fs1 to {ty}")
        if a2_is_const:
            opx.append(f"  %{tag}f2 = bitcast {'i32' if ty=='float' else 'i64'} {a2} to {ty}")
        else:
            opx.append(f"  %{tag}fs2 = trunc i128 {a2} to {'i64' if kind=='d' else 'i32'}")
            opx.append(f"  %{tag}f2 = bitcast {'i64' if kind=='d' else 'i32'} %{tag}fs2 to {ty}")
        opx.append(f"  %{tag}lt = fcmp ult {ty} %{tag}f1, %{tag}f2")
        opx.append(f"  %{tag}eq = fcmp ueq {ty} %{tag}f1, %{tag}f2")
        opx.append(f"  %{tag}uord = fcmp uno {ty} %{tag}f1, %{tag}f2")
        opx.append(f"  %{tag}cf = or i1 %{tag}lt, %{tag}uord")
        opx.append(f"  %{tag}zf = or i1 %{tag}eq, %{tag}uord")
        opx.append(f"  %{tag}pf = and i1 %{tag}uord, %{tag}uord")
        # (a) 直後の br
        repl = []
        j = idx + 1
        while j < min(idx + 13, len(lines)):
            l2 = lines[j]
            if re.match(r"^  br i1 %", l2):
                m2 = re.match(r"^  br i1 (i1 )?%([\w.\-]+), label", l2) or re.match(r"^  br i1 %([\w.\-]+), label", l2)
                if m2:
                    if m2.group(2).startswith('cf.'):
                        repl.append((j, m2.group(2), f"%{tag}cf"))
                        hits['br_cf'] += 1
                    elif m2.group(2).startswith('zf.'):
                        repl.append((j, m2.group(2), f"%{tag}zf"))
                        hits['br_zf'] += 1
                    elif m2.group(2).startswith('pf.'):
                        repl.append((j, m2.group(2), f"%{tag}pf"))
                        hits['br_pf'] += 1
                    elif re.search(r'cf\.|zf\.|pf\.', m2.group(2)):
                        repl.append((j, m2.group(2), f"%{tag}cf"))
                        hits['br_?'] += 1
                    else:
                        hits['br_other'] += 1
                break
            if re.match(r"^  %[\w.\-]+ = or i1 %[\w.\.-]+, %[\w.\.-]+$", l2):
                mm = re.match(r"^  %([\w.\-]+) = or i1 %([\w.\-]+), %([\w.\-]+)(.*)$", l2)
                a, b = mm.group(2), mm.group(3)
                if 'cf.' in a and 'zf.' in b:
                    repl.append((j, a, f"%{tag}cf"))
                    repl.append((j, b, f"%{tag}zf"))
                    hits['or_cfzf'] += 1
                    break
                elif 'zf.' in a and 'cf.' in b:
                    repl.append((j, a, f"%{tag}zf"))
                    repl.append((j, b, f"%{tag}cf"))
                    hits['or_zfcf'] += 1
                    break
            if re.match(r"^  call void @__asm_", l2):
                break
            j += 1
        if not repl:
            hits['no_branch'] += 1
            continue
        inserts[idx] = (opx, repl)
    print('[P1] 修復 insert site:', len(inserts))
    print('   hits:', dict(hits))
    # apply
    out = []
    for i, l in enumerate(lines):
        if i in inserts:
            opx, repl = inserts[i]
            out += opx
            out.append(l)
        else:
            out.append(l)
    repmap = {}
    for (idx, repl) in inserts.values():
        for (j, old, new) in repl:
            repmap.setdefault(j, []).append((old, new))
    for j, repls in sorted(repmap.items()):
        ln = out[j]
        for (old, new) in repls:
            ln = ln.replace(old, new, 1)
        out[j] = ln
    open(dst, 'w').write('\n'.join(out))
    print('[P1] wrote', dst)


if __name__ == '__main__':
    main()
