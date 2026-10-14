#!/usr/bin/env python3
"""frame_slot_probe.py — 付録 REPORT_APPENDIX_2394.md (ICALL-75 #2394) の再現。
  mc     : 元 PE の decode 結果 (before.0.drc.dsm) の 1 関数を capstone で再 decode し、rbp 相対 store を列挙。
           rw.dll (元 PE + .icall) の同 VA の bytes と一致するかも出す。
  phase  : retdec-decompiler --print-after-all の stderr を段ごとに割り、1 関数の stack_var alloca の store/load/ptrtoint を追う。
  restore: 回復実験用 (--separate で -24 と -16 を別 alloca のままにする負の対照)。after.0.restored.ll の function_181057b38 に、脱落した 2 store ([rbp-8]・[rbp-0x20]) を戻した IR を書く。
           [rbp-0x10] と [rbp-8] は callee が [r8+8] で読むため、1 つの 16B alloca (stack_var_-24 の下位・上位 8B) に置く。
  census : F.ranges の関数群で、機械語の rbp 相対 store のうち、before.0.drc.ll に同 insn.addr の store が無いもの (脱落) を数える。
           脱落 store の slot が、lea [rbp+e] で address を取られた slot の 0x40 以内上側にあるものを「候補」として別に数える。
"""
import argparse, re, sys

def dsm_funcs(path, wanted=None):
    """{start_va: [(addr, bytes)]} を返す。wanted が与えられたら、その VA の関数だけを読む。"""
    out, cur = {}, None
    ins = re.compile(r'^0x([0-9a-f]+):\s+((?:[0-9a-f]{2} )+)\s*\t')
    fn = re.compile(r'^; function: \S+ at 0x([0-9a-f]+) -- 0x([0-9a-f]+)')
    with open(path, errors='replace') as f:
        for line in f:
            if line.startswith('; '):
                m = fn.match(line)
                if m:
                    va = int(m.group(1), 16)
                    cur = out.setdefault(va, []) if (wanted is None or va in wanted) else None
                else:
                    cur = None
                continue
            if cur is None or '|' in line:
                continue
            m = ins.match(line)
            if m:
                cur.append((int(m.group(1), 16), bytes.fromhex(m.group(2).strip())))
    return out

def cs():
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    return capstone, md

def frame_ops(insns):
    """(rbp 相対 store [(addr, disp, size, text)], lea で address を取られた rbp slot [(addr, disp)], rbp を frame pointer にしているか)"""
    capstone, md = cs()
    from capstone import x86
    stores, leas, fp = [], [], False
    for addr, b in insns:
        for i in md.disasm(b, addr):
            ops = i.operands
            if len(ops) == 2 and ops[0].type == x86.X86_OP_REG and ops[0].reg == x86.X86_REG_RBP and (
                    (i.mnemonic == 'mov' and ops[1].type == x86.X86_OP_REG and ops[1].reg == x86.X86_REG_RSP) or
                    (i.mnemonic == 'lea' and ops[1].type == x86.X86_OP_MEM and ops[1].mem.base == x86.X86_REG_RSP)):
                fp = True
            if i.mnemonic == 'mov' and len(ops) == 2 and ops[0].type == x86.X86_OP_MEM \
                    and ops[0].mem.base == x86.X86_REG_RBP and ops[0].mem.index == 0:
                stores.append((i.address, ops[0].mem.disp, ops[0].size, '%s %s' % (i.mnemonic, i.op_str)))
            elif i.mnemonic == 'lea' and len(ops) == 2 and ops[1].type == x86.X86_OP_MEM \
                    and ops[1].mem.base == x86.X86_REG_RBP and ops[1].mem.index == 0:
                leas.append((i.address, ops[1].mem.disp))
    return stores, leas, fp

def cmd_mc(a):
    va = int(a.va, 16)
    fn = dsm_funcs(a.dsm, {va})[va]
    raw = b''.join(b for _, b in fn)
    lo, hi = fn[0][0], fn[-1][0] + len(fn[-1][1])
    print('dsm: function 0x%x  %d insn  %d B  [0x%x, 0x%x)' % (va, len(fn), len(raw), lo, hi))
    stores, leas, fp = frame_ops(fn)
    print('  rbp を frame pointer にする prologue (mov rbp,rsp / lea rbp,[rsp+..]): %s' % ('あり' if fp else 'なし'))
    for ad, d, sz, t in stores:
        print('  store 0x%x  [rbp%+#x] %dB   %s' % (ad, d, sz, t))
    for ad, d in leas:
        print('  lea   0x%x  &[rbp%+#x]' % (ad, d))
    if a.pe:
        import pefile
        pe = pefile.PE(a.pe)
        got = pe.get_data(lo - pe.OPTIONAL_HEADER.ImageBase, hi - lo)
        print('%s の VA 0x%x..0x%x: dsm の bytes と %s' % (a.pe, lo, hi, '一致' if got == raw else '不一致'))
        sys.exit(0 if got == raw else 1)

def cmd_phase(a):
    t = open(a.err, errors='replace').read()
    parts = re.split(r'^\*\*\* IR Dump After (.*) \*\*\*$', t, flags=re.M)
    slots = a.slots.split(',')
    last = None
    print('%-48s %s' % ('段 (遷移した所だけ)', ' '.join('%s(alloca/store/load/ptrtoint)' % s for s in slots)))
    for i in range(1, len(parts), 2):
        name, body = parts[i], parts[i + 1]
        m = re.search(r'^define [^\n]*@%s\b[^\n]*\{\n(.*?)^\}' % re.escape(a.func), body, flags=re.M | re.S)
        if not m:
            continue
        f = m.group(1)
        row = []
        for s in slots:
            v = r'%%stack_var_%s\b' % re.escape(s)
            row.append((len(re.findall(v + ' = alloca', f)), len(re.findall(r'\bstore [^\n]*' + v, f)),
                        len(re.findall(r'= load [^\n]*' + v, f)), len(re.findall(r'ptrtoint [^\n]*' + v, f))))
        if row != last:
            print('%-48s %s' % (name, ' '.join('%s=%s' % (s, '/'.join(map(str, r))) for s, r in zip(slots, row))))
            last = row

def cmd_restore(a):
    t = open(a.src, errors='replace').read()
    m = re.search(r'^define [^\n]*@function_181057b38\(\)[^\n]*\{\n.*?^\}', t, flags=re.M | re.S)
    f = m.group(0)
    old_alloca = '  %stack_var_-24 = alloca i64, align 8\n'
    old_store = '  store i64 %9, i64* %stack_var_-24, align 8, !insn.addr !6585\n'
    assert f.count(old_alloca) == 1 and f.count(old_store) == 1
    if a.separate:  # 負の対照: store は戻すが、-24 と -16 を別 alloca のままにする
        new = ('  %stack_var_-24 = alloca i64, align 8\n  %stack_var_-16 = alloca i64, align 8\n'
               '  %stack_var_-40 = alloca i64, align 8\n')
    else:
        new = ('  %fa_pair = alloca i128, align 16\n'
               '  %stack_var_-24 = bitcast i128* %fa_pair to i64*\n'
               '  %fa_pair_i = ptrtoint i128* %fa_pair to i64\n'
               '  %fa_pair_h = add i64 %fa_pair_i, 8\n'
               '  %stack_var_-16 = inttoptr i64 %fa_pair_h to i64*\n'
               '  %stack_var_-40 = alloca i64, align 8\n')
    g = f.replace(old_alloca, new)
    g = g.replace(old_store, old_store + (
        '  store i64 ptrtoint (i64* @global_var_181306ce0 to i64), i64* %stack_var_-40, align 8\n'
        '  %fa_p40 = ptrtoint i64* %stack_var_-40 to i64\n'
        '  store i64 %fa_p40, i64* %stack_var_-16, align 8\n'))
    open(a.out, 'w').write(t.replace(f, g))
    print('wrote', a.out)

def ll_store_addrs(path):
    """{関数 VA: set(store の insn.addr)}"""
    t = open(path, errors='replace').read()
    md = {int(n): int(v) for n, v in re.findall(r'^!(\d+) = !\{i64 (\d+)\}', t, flags=re.M)}
    out = {}
    for m in re.finditer(r'^define [^\n]*@function_([0-9a-f]+)\([^\n]*\{\n(.*?)^\}', t, flags=re.M | re.S):
        s = set()
        for l in m.group(2).split('\n'):
            if re.search(r'\bstore\b', l):
                k = re.search(r'!insn\.addr !(\d+)', l)
                if k:
                    s.add(md[int(k.group(1))])
        out[int(m.group(1), 16)] = s
    return out

def cmd_census(a):
    ranges = [r for r in open(a.ranges).read().strip().split(',') if r]
    wanted = {int(r.split('-')[0], 16) for r in ranges}
    fns = dsm_funcs(a.dsm, wanted)
    irs = ll_store_addrs(a.ll)
    nf = nfr = nst = ndrop = ncand = nnofp = 0
    cand_fns, rows = {}, []
    for va in sorted(wanted):
        insns = fns.get(va) or []
        if not insns:
            continue
        nf += 1
        stores, leas, fp = frame_ops(insns)
        if not stores and not leas:
            continue
        if not fp:
            nnofp += 1
            continue
        nfr += 1
        have = irs.get(va, set())
        for ad, d, sz, t in stores:
            nst += 1
            if ad in have:
                continue
            ndrop += 1
            esc = [e for _, e in leas if 0 < d - e <= 0x40]
            if esc:
                ncand += 1
                cand_fns.setdefault(va, []).append((ad, d, sz, t, max(esc)))
    print('F 関数 %d (dsm に命令あり %d) / rbp 相対 store か lea を持つ関数のうち frame pointer 型 %d・rbp を汎用 reg に使う型 (除外) %d' % (len(wanted), nf, nfr, nnofp))
    print('frame pointer 型の rbp 相対 mov store %d 件 / IR に同 insn.addr の store が無い (脱落) %d 件' % (nst, ndrop))
    print('脱落のうち、lea で address を取られた slot の 0x40 以内上側にあるもの (候補) %d 件 / %d 関数' % (ncand, len(cand_fns)))
    for va, l in sorted(cand_fns.items()):
        for ad, d, sz, t, e in l:
            print('  fn 0x%x  store 0x%x [rbp%+#x] %dB  (%s)  直下の escaped slot [rbp%+#x]' % (va, ad, d, sz, t, e))

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest='cmd', required=True)
    q = sp.add_parser('mc'); q.add_argument('--dsm', required=True); q.add_argument('--va', required=True); q.add_argument('--pe'); q.set_defaults(f=cmd_mc)
    q = sp.add_parser('phase'); q.add_argument('--err', required=True); q.add_argument('--func', required=True)
    q.add_argument('--slots', default='-16,-40,-24,-56,-52'); q.set_defaults(f=cmd_phase)
    q = sp.add_parser('census'); q.add_argument('--dsm', required=True); q.add_argument('--ll', required=True); q.add_argument('--ranges', required=True); q.set_defaults(f=cmd_census)
    q = sp.add_parser('restore'); q.add_argument('--src', required=True); q.add_argument('--out', required=True); q.add_argument('--separate', action='store_true'); q.set_defaults(f=cmd_restore)
    a = p.parse_args(); a.f(a)
