#!/usr/bin/env python3
"""frame_slot_restore.py — 脱落した frame slot store を IR に戻し、隣接 slot を 1 つの alloca にまとめる pass (ICALL-77 #2427)。

  入力: 復元後 IR (after.0.restored.ll)・元の機械語 (before.0.drc.dsm)・元の IR (before.0.drc.ll)・F.ranges
  検出: frame_slot_probe.py census と同じ定義。rbp 相対の 8B store のうち、before IR に同じ insn.addr の store が無く、
        lea で address を取られた slot e に対し 0 < d - e <= 0x40 を満たすもの (候補)。
  値  : 候補 store の source reg を、同一基本ブロック内で最後に書いた命令から解決する。
        lea [rbp+e] なら frame slot の address、lea [rip+x] なら global の VA。解決できなければ戻さない。
  復元: RetDec の命名 stack_var_X は X = disp - 8。候補の slot X の alloca が無ければ、直下 X-8 が lea で取られた i64 alloca の
        ときは両者を 16B の 1 alloca にまとめる (X-8 が下位・X が上位)。そうでなければ alloca i64 を足す。
        値の store は、insn.addr が元 VA より大きい最初の IR 命令の直前に挿入する。
        その直前までに基本ブロックの境界 (label・terminator) があるときは戻さない (挿入点の所属ブロックが決まらないため)。
  出力: 復元後 IR と、関数ごとの検出・解決・適用の JSON (--report)。
"""
import argparse, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frame_slot_probe as fsp


def _gpr_map():
    m = {}
    for b in ('ax', 'bx', 'cx', 'dx', 'si', 'di', 'bp', 'sp'):
        for n in ('r' + b, 'e' + b, b):
            m[n] = 'r' + b
    for b in 'abcd':
        m[b + 'l'] = m[b + 'h'] = 'r%sx' % b
    for b in ('si', 'di', 'bp', 'sp'):
        m[b + 'l'] = 'r' + b
    for i in range(8, 16):
        for suf in ('', 'd', 'w', 'b'):
            m['r%d%s' % (i, suf)] = 'r%d' % i
    return m


GPR = _gpr_map()


def decode(fn):
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    return [i for addr, b in fn for i in md.disasm(b, addr)]


def resolve(insns, k, reg64, targets):
    """insns[k] の store が使う reg64 の値を、同一基本ブロック内の直前の定義から解決する。"""
    from capstone import x86 as X
    if insns[k].address in targets:
        return None
    for j in range(k - 1, -1, -1):
        i = insns[j]
        ops = i.operands
        if i.mnemonic.startswith('j') or i.mnemonic.startswith('ret') or i.mnemonic in ('call', 'loop', 'int3'):
            return None
        if ops and ops[0].type == X.X86_OP_REG and GPR.get(i.reg_name(ops[0].reg)) == reg64:
            if i.mnemonic == 'lea' and len(ops) == 2 and ops[1].type == X.X86_OP_MEM:
                m = ops[1].mem
                if m.base == X.X86_REG_RBP and m.index == 0:
                    return ('frame', m.disp)
                if m.base == X.X86_REG_RIP and m.index == 0:
                    return ('global', i.address + i.size + m.disp)
            return None
        if i.address in targets:
            return None
    return None


def scan(insns, before_addrs):
    """(候補の一覧, 戻す store の一覧, lea で取られた slot の stack X 集合)"""
    from capstone import x86 as X
    targets = set()
    for i in insns:
        if i.mnemonic.startswith('j') and i.operands and i.operands[0].type == X.X86_OP_IMM:
            targets.add(i.operands[0].imm)
    leas, stores = [], []
    for k, i in enumerate(insns):
        ops = i.operands
        if i.mnemonic == 'lea' and len(ops) == 2 and ops[1].type == X.X86_OP_MEM and ops[1].mem.base == X.X86_REG_RBP and ops[1].mem.index == 0:
            leas.append(ops[1].mem.disp)
        if i.mnemonic == 'mov' and len(ops) == 2 and ops[0].type == X.X86_OP_MEM and ops[0].mem.base == X.X86_REG_RBP and ops[0].mem.index == 0:
            stores.append(k)
    escaped = {e - 8 for e in leas}
    cands, restores = [], []
    for k in stores:
        i = insns[k]
        d, size, src = i.operands[0].mem.disp, i.operands[0].size, i.operands[1]
        if i.address in before_addrs:
            continue
        esc = [e for e in leas if 0 < d - e <= 0x40]
        if not esc:
            continue
        ent = {'va': '0x%x' % i.address, 'disp': d, 'size': size, 'insn': i.mnemonic + ' ' + i.op_str}
        reg64 = GPR.get(i.reg_name(src.reg)) if src.type == X.X86_OP_REG else None
        val = resolve(insns, k, reg64, targets) if (size == 8 and reg64) else None
        ent['value'] = list(val) if val else None
        cands.append(ent)
        if val:
            restores.append((i.address, d - 8, val[0], val[1]))
    return cands, restores, escaped


def edit(fn, restores, escaped, md, gl_text):
    lines = fn.split('\n')
    log = {'restored': [], 'merged': [], 'created': [], 'skipped': []}
    merged_low = set()

    def allocas():
        out = {}
        for i, l in enumerate(lines):
            m = re.match(r'  %stack_var_(-?\d+) = alloca (\w+), align \d+$', l)
            if m:
                out[int(m.group(1))] = (i, m.group(2))
        return out

    known = {x: t for x, (_, t) in allocas().items()}

    def ensure(X):
        if X in known:
            return known[X]
        al = allocas()
        E = X - 8
        if E in escaped and E in al and known.get(E) == 'i64' and E not in merged_low:
            i = al[E][0]
            lines[i:i + 1] = [
                '  %%fs_pair_%d = alloca i128, align 16' % E,
                '  %%stack_var_%d = bitcast i128* %%fs_pair_%d to i64*' % (E, E),
                '  %%fs_pair_%d_i = ptrtoint i128* %%fs_pair_%d to i64' % (E, E),
                '  %%fs_pair_%d_h = add i64 %%fs_pair_%d_i, 8' % (E, E),
                '  %%stack_var_%d = inttoptr i64 %%fs_pair_%d_h to i64*' % (X, E),
            ]
            merged_low.add(E)
            known[E] = known[X] = 'i64'
            log['merged'].append([E, X])
            return 'i64'
        last = max([i for i, _ in al.values()] or [0])
        lines.insert(last + 1, '  %%stack_var_%d = alloca i64, align 8' % X)
        known[X] = 'i64'
        log['created'].append(X)
        return 'i64'

    def body_pos(addr):
        for i, l in enumerate(lines):
            m = re.search(r'!insn\.addr !(\d+)', l)
            if m and 'alloca' not in l and md.get(int(m.group(1)), 0) > addr:
                return i
        for i, l in enumerate(lines):
            if l.startswith('  ret '):
                return i
        return len(lines) - 1

    def same_block(p):
        for j in range(p - 1, -1, -1):
            l = lines[j]
            if re.match(r'^(?:[A-Za-z0-9_.$-]+:|;\s*<label>:)', l) or re.match(r'^\s+(br|switch|ret|unreachable|indirectbr)\b', l):
                return False
            if '!insn.addr' in l and 'alloca' not in l:
                return True
        return True

    for addr, Xt, kind, pv in sorted(restores):
        if not same_block(body_pos(addr)):
            log['skipped'].append(['0x%x' % addr, 'block boundary before insertion point'])
            continue
        if ensure(Xt) != 'i64':
            log['skipped'].append(['0x%x' % addr, 'target slot not i64'])
            continue
        if kind == 'frame':
            Xv = pv - 8
            if ensure(Xv) != 'i64':
                log['skipped'].append(['0x%x' % addr, 'value slot not i64'])
                continue
            vref = '%%fs_val_%x' % addr
            pre = ['  %s = ptrtoint i64* %%stack_var_%d to i64' % (vref, Xv)]
        else:
            if '@global_var_%x = ' % pv not in gl_text:
                log['skipped'].append(['0x%x' % addr, 'global not in IR'])
                continue
            vref = 'ptrtoint (i64* @global_var_%x to i64)' % pv
            pre = []
        store = '  store i64 %s, i64* %%stack_var_%d, align 8' % (vref, Xt)
        p = body_pos(addr)
        lines[p:p] = pre + [store]
        log['restored'].append(['0x%x' % addr, Xt, kind, pv])
    return '\n'.join(lines), log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ir', required=True, help='復元後 IR (after.0.restored.ll)')
    ap.add_argument('--dsm', required=True, help='元 PE の decode 結果 (before.0.drc.dsm)')
    ap.add_argument('--before-ll', required=True, help='元 PE の IR (before.0.drc.ll)')
    ap.add_argument('--ranges', required=True, help='F.ranges (カンマ区切り)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--report')
    a = ap.parse_args()
    ranges = [r for r in open(a.ranges).read().strip().split(',') if r]
    wanted = {int(r.split('-')[0], 16) for r in ranges}
    fns = fsp.dsm_funcs(a.dsm, wanted)
    irb = fsp.ll_store_addrs(a.before_ll)
    text = open(a.ir, errors='replace').read()
    md = {int(n): int(v) for n, v in re.findall(r'^!(\d+) = !\{i64 (\d+)\}', text, flags=re.M)}
    rep = {}
    for va in sorted(wanted):
        raw = fns.get(va) or []
        if not raw or not fsp.frame_ops(raw)[2]:
            continue
        insns = decode(raw)
        cands, restores, escaped = scan(insns, irb.get(va, set()))
        if not cands:
            continue
        ent = {'candidates': cands, 'restore_n': len(restores)}
        m = re.search(r'^define [^\n]*@function_%x\(.*?^\}' % va, text, flags=re.M | re.S)
        if not m:
            ent['skip'] = 'IR に関数が無い'
            rep['0x%x' % va] = ent
            continue
        if restores:
            new_fn, log = edit(m.group(0), restores, escaped, md, text)
            text = text.replace(m.group(0), new_fn, 1)
            ent.update(log)
        rep['0x%x' % va] = ent
    open(a.out, 'w').write(text)
    out = json.dumps(rep, indent=1)
    if a.report:
        open(a.report, 'w').write(out + '\n')
    n_c = sum(len(v['candidates']) for v in rep.values())
    n_r = sum(v.get('restore_n', 0) for v in rep.values())
    print('[frame_slot_restore] 候補 %d 件 (解決して戻す %d 件) -> %s' % (n_c, n_r, a.out), file=sys.stderr)


if __name__ == '__main__':
    main()
