#!/usr/bin/env python3
"""fix_xmm_args.py [P-X1]: RetDec が落とす xmm 引数 ((DEFECTS.md) D5) の汎用復元 (PLG-F2-4 #547)。

  python3 fix_xmm_args.py IN.ll OUT.ll --pe PE [--report r.json] [--skip-funcs a,b]

機械語 (p0c/k80abi.py scan_function = win64 slot の read-before-write) で関数ごとの xmm 入力 slot を求め、
p0c/k80_argfix.py の [A] movd-from-zero / [C] helper 被演算子の placeholder (`xor i128 0, 0`) 接続を再利用する。
k80_argfix は引数を `i64 %in.xmmN.bits` として末尾に足す (kernel の k80_diff 用)。本 pass は、それを
**Win64 の slot 位置 N に float/double 型で置き直す** (位置 N → xmm N。slot の隙間は未使用 i64 で埋める)。
こうすると IR 署名が機械語 ABI と一致し、tools/liftdiff の native/wasm 両側が同じ位置規約で渡せる。

適用しない関数 (report の `skipped` に理由付きで出す。黙って変えない):
  (closure 内の呼出し元は call site に引数を足す。呼出し元の xmm 値は本 pass では復元できないので **0 / 0.0 を渡す**
   (= 従来の placeholder と同じ値)。件数は report の `callsite_zero_args` に出す。値の接続は呼出し元側の xmm データフロー復元が要る (未解決)。)
  - 既に位置 N に引数がある (RetDec が xmm 位置を整数引数として宣言済み)        : 'slot_occupied'
  - 接続できる placeholder が無い                                                : 'no_placeholder'
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'p0c'))
import k80_argfix as KA  # noqa: E402
import k80abi as K  # noqa: E402
from capstone import Cs, CS_ARCH_X86, CS_MODE_64  # noqa: E402
import pefile  # noqa: E402


def split_defs(text):
    starts = [m.start() for m in re.finditer(r'(?m)^define [^\n]*\{', text)]
    head = text[:starts[0]] if starts else text
    chunks = []
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(text)
        seg = text[s:e]
        nl = seg.index('\n') + 1
        rest = seg[nl:]
        mc = rest.rindex('\n}\n')
        chunks.append([seg[:nl], rest[:mc], rest[mc + 3:]])
    return head, chunks


def params_of(header):
    m = re.search(r'\(([^)]*)\)', header)
    s = m.group(1).strip() if m else ''
    return [p.strip() for p in s.split(',')] if s else []


def set_params(header, plist):
    return re.sub(r'\(([^)]*)\)', '(' + ', '.join(plist) + ')', header, count=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--report')
    ap.add_argument('--skip-funcs', default='')
    a = ap.parse_args()
    skip = set(x for x in a.skip_funcs.split(',') if x)
    text = open(a.src, errors='replace').read()
    base, F, tva, td = K.load_pe(a.pe)
    pe = pefile.PE(a.pe, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    MD = Cs(CS_ARCH_X86, CS_MODE_64)
    MD.detail = True
    head, chunks = split_defs(text)
    callers = {}
    for ln in text.split('\n'):
        if ln.startswith('define '):
            continue
        for m in re.finditer(r'@(function_[0-9a-f]+)\(', ln):
            callers[m.group(1)] = callers.get(m.group(1), 0) + 1
    rep = {'fixed': {}, 'skipped': {}, 'movd_sites': {}, 'movd_fixed': 0, 'orphan_float_fixed': 0,
           'orphan_gpr_fixed': 0, 'helper_xmm_fixed': 0, 'struct_copy_fixed': 0}
    out = [head]
    added = {}
    for header, body, inter in chunks:
        fname = KA.func_name(header)
        done = False
        if fname and fname.startswith('function_') and fname not in skip:
            va = int(fname.split('_')[1], 16)
            fend = F.get(va)
            if fend is None:
                rep['skipped'][fname] = 'no_pdata'
            else:
                g, x, gd, gb, gx, xw, st, xins, sci, cli, ps = K.scan_function(MD, td, tva, va, fend)
                xs = [s for s in x if int(s[3:]) < 4]
                if xs:
                    habi = {'xmm_slots': xs, 'xmm_width': xw, 'xmm_insns': [[m, r] for m, r in xins]}
                    if True:
                        plist = params_of(header)
                        occ = [s for s in xs if len(plist) > int(s[3:])]
                        if occ:
                            rep['skipped'][fname] = 'slot_occupied(%s, IR params=%d)' % (','.join(occ), len(plist))
                        else:
                            h2, b2, c1 = KA.fix_movd_from_zero(header, body, habi, rep, fname)
                            h3, b3, c2 = KA.fix_helper_operand_xmm(h2, b2, habi, rep, fname)
                            if not (c1 or c2):
                                rep['skipped'][fname] = 'no_placeholder'
                            else:
                                # k80_argfix が末尾に足した `i64 %in.xmmN.bits` を slot 位置 N の float/double 型に置換
                                plist0 = params_of(header)
                                newp = params_of(h3)[len(plist0):]
                                slots = {}
                                for p in newp:
                                    m = re.match(r'i64 %in\.(xmm\d)\.bits$', p)
                                    slots[int(m.group(1)[3:])] = m.group(1)
                                full = list(plist0)
                                for n in sorted(slots):
                                    while len(full) < n:
                                        full.append('i64 %%pad%d' % len(full))
                                    nm = slots[n]
                                    w = xw.get(nm, 32)
                                    ty = 'double' if w == 64 else 'float'
                                    full.append('%s %%in.%s' % (ty, nm))
                                    bits = '%%in.%s.bits' % nm
                                    if w == 64:
                                        b3 = b3.replace('zext i64 %s to i128' % bits,
                                                        'zext i64 %%in.%s.i to i128' % nm)
                                        b3 = re.sub(r'(?m)^(\s*)(%[\w.$-]+ = zext i64 %in\.' + nm + r'\.i to i128)$',
                                                    r'\1%in.' + nm + r'.i = bitcast double %in.' + nm + r' to i64\n\1\2', b3, count=1)
                                    else:
                                        b3 = b3.replace('trunc i64 %s to i32' % bits,
                                                        'bitcast float %%in.%s to i32' % nm)
                                header, body = set_params(h3, full), b3
                                rep['fixed'][fname] = {'params': full, 'callers': callers.get(fname, 0)}
                                added[fname] = full[len(plist0):]
                                done = True
        out.append(header + body + '\n}\n' + inter)
    res = ''.join(out)
    zero = 0
    for fn, extra in added.items():
        zs = ', '.join('%s %s' % (p.split()[0], '0.0' if p.split()[0] in ('float', 'double') else '0') for p in extra)

        def sub(m, zs=zs):
            nonlocal zero
            zero += 1
            return m.group(1) + (m.group(2) + ', ' if m.group(2).strip() else '') + zs + ')'
        res = re.sub(r'(?m)^(?!define )(.*?call [^@\n]*@%s\()([^)]*)\)' % fn, sub, res)
    rep['callsite_zero_args'] = zero
    open(a.dst, 'w').write(res)
    if a.report:
        json.dump(rep, open(a.report, 'w'), ensure_ascii=False, indent=1)
    print('[fix_xmm_args] fixed=%d skipped=%d %s' % (len(rep['fixed']), len(rep['skipped']),
                                                    json.dumps(rep['skipped'], ensure_ascii=False)[:300]))


if __name__ == '__main__':
    main()
