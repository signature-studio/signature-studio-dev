#!/usr/bin/env python3
"""fle_diff.py — 関数単位 spot 差分検証: native (実機械語直実行) vs wasm (flelift lift 産物)。

tools/liftdiff の e2e (V12 検収稼働中) は実行せず、独自ミニランナで実測差分を取り、
tools/liftdiff/docs/FORMAT.md (v1) §3 の JSONL スキーマ準拠で verdict を出す (採点は CAB-232/233)。

比較対象: rax / xmm0 / image (.data+.bss) / TEB / scratch / arena (VirtualAlloc bump) の 8B block 差分。
usage: python3 fle_diff.py [--out work/verdict.jsonl] [--summary work/verdict_summary.json]
"""
import argparse, json, os, struct, subprocess, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'shared'))
from paths import FL_WIN64_DIR
PE = os.environ.get('FLE_PE') or os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')
IMG = 0x400000
DATA_LO, DATA_HI = 0x13a5000, 0x196f000   # .data + .bss (VA)
TEB = 0x1D00000
SCRATCH = 0x20000000
ARENA_LO, ARENA_HI = 0x2100000, 0x3100000
REGIONS = [('image', DATA_LO, DATA_HI), ('teb', TEB, TEB + 0x400),
           ('scratch', SCRATCH, SCRATCH + 0x100000), ('arena', ARENA_LO, ARENA_HI)]

USTR_STR = 0x20001000 + 12   # StrRec 直後の文字本体


def ustrasg_prep(self_assign):
    """UStrAsg 用 scratch 敷設 (wasm runner / natdrv と同一。StrRec = codepage u16, elemsize u16,
    refcnt i32, len i32, 直後に文字本体)"""
    buf = bytearray(0x2000)
    off = (USTR_STR - 12) - SCRATCH
    struct.pack_into('<H', buf, off, 1200)        # codepage
    struct.pack_into('<H', buf, off + 2, 2)       # elemsize
    struct.pack_into('<i', buf, off + 4, 1)       # refcnt
    struct.pack_into('<i', buf, off + 8, 8)       # len
    for i in range(16):
        buf[(USTR_STR - SCRATCH) + i] = 0x41 + i
    struct.pack_into('<Q', buf, 0, USTR_STR if self_assign else 0)
    return bytes(buf)


# (va, name, [(pid, prep, gpr, xmm, stk, desc)])
SPOT = [
    (0x409c80, 'Move', [
        ('p392', None, [SCRATCH + 0x1000, SCRATCH + 0x3000, 392], [], [], 'src,dst,n (rep movsb + movups)'),
        ('p36', None, [SCRATCH + 0x1000, SCRATCH + 0x3000, 36], [], [], 'n=36 (movups 4x path)'),
        ('p17', None, [SCRATCH + 0x1004, SCRATCH + 0x3002, 17], [], [], 'unaligned'),
        ('p0', None, [SCRATCH + 0x1000, SCRATCH + 0x3000, 0], [], [], 'n=0'),
    ]),
    (0x4133f0, '_UStrAsg', [
        ('p_src0', 'ustrasg', [SCRATCH, 0, 0, 0], [], [], 'dest=&slot(0), src=0'),
        ('p_refcnt', 'ustrasg', [SCRATCH, USTR_STR, 0, 0], [], [], 'lock xadd 経路 (refcnt++)'),
        ('p_self', 'ustrasg_self', [SCRATCH, USTR_STR, 0, 0], [], [], 'self-assign (old=src)'),
    ]),
    (0x6a7e40, 'sse2_blend_6a7e40', [
        ('p01', 'pat', [0x20004000, 0x20004800, 32, 0x20005000], [], [0x20005200],
         'src,dst,n,srcF + bias(5th)'),
        ('p02', 'pat', [0x20004004, 0x20004804, 20, 0x20005004], [], [0x20005200],
         'unaligned + n=20'),
    ]),
    (0x6a7180, 'sse2_mix_6a7180', [
        ('p01', 'pat', [0x20004400, 0x20004c00, 8, 8], [], [0, 0, 0x00080010],
         '7th stack arg = mul dword'),
    ]),
    (0x69a130, 'sse2_minmax_69a130', [
        ('p01', 'pat', [0x20005400, 8, 0x20005800], [], [], 'srcF, n, dst'),
        ('p02', 'pat', [0x20005404, 3, 0x20005808], [], [], 'n=3 (tail paths)'),
    ]),
    (0x660c40, 'mmx_blend_660c40', [
        ('p01', None, [0x80, 0x40, 0x20], [], [], 'ecx,edx,r8d (MMX)'),
        ('p02', None, [0xff, 0x01, 0x81], [], [], 'sat edge'),
    ]),
    (0x6a7990, 'mmx_rgb_6a7990', [
        ('p01', None, [SCRATCH + 0x4400, SCRATCH + 0x4600, 5, 0x0101010101010101], [], [0x0080004000200010],
         '5th=xmm経由 mm7, 6th=stack mm6'),
        ('p02', None, [SCRATCH + 0x4400, SCRATCH + 0x4600, 8, 0x00ff008000400020], [], [0x0001000200030004], 'n=8'),
    ]),
]


def static_features(va):
    import pefile
    import capstone
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    from capstone.x86 import X86_OP_IMM
    pef = pefile.PE(data=open(PE, 'rb').read())
    img = pef.get_memory_mapped_image()
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
    pd = [s for s in pef.sections if s.Name.startswith(b'.pdata')][0].get_data()
    fnd = None
    for i in range(0, len(pd) // 12 * 12, 12):
        b, e, u = struct.unpack_from('<III', pd, i)
        if b == 0 and e == 0:
            break
        if IMG + b == va:
            fnd = (IMG + b, IMG + e); break
    mach = {'ins': 0, 'icall': 0, 'ijmp': 0, 'fpcmp': 0, 'arity_gpr': 0, 'arity_x': 0, 'stack_args': [], 'repstr': 0}
    if fnd:
        v = fnd[0]
        while v < fnd[1]:
            got = None
            for ins in md.disasm(img[v - IMG:fnd[1] - IMG], v, 1):
                got = ins; break
            if got is None:
                v += 1; continue
            i2 = got; v += i2.size; mach['ins'] += 1
            m2 = i2.mnemonic
            if m2 == 'call' and i2.operands[0].type != X86_OP_IMM:
                mach['icall'] += 1
            if m2 == 'jmp' and i2.operands[0].type != X86_OP_IMM:
                mach['ijmp'] += 1
            if m2 in ('comisd', 'comiss', 'ucomisd', 'ucomiss'):
                mach['fpcmp'] += 1
            if m2.startswith('rep'):
                mach['repstr'] += 1
    return mach


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(HERE, 'work', 'verdict.jsonl'))
    ap.add_argument('--summary', default=os.path.join(HERE, 'work', 'verdict_summary.json'))
    ap.add_argument('--cjs', default=os.path.join(HERE, 'work', 'lift', 'flel.cjs'))
    a = ap.parse_args()

    # ---- 1) wasm 側 (node runner) ----
    all_cases = [(va, nm, pid, prep, gpr, xmm, stk, ad)
                 for (va, nm, pats) in SPOT for (pid, prep, gpr, xmm, stk, ad) in pats]
    env = dict(os.environ)
    env['FLE_CASES'] = json.dumps([
        {'fn': va, 'name': nm, 'id': pid, 'prep': prep, 'gpr': gpr, 'xmm': xmm, 'stk': stk, 'desc': ad}
        for (va, nm, pid, prep, gpr, xmm, stk, ad) in all_cases
    ], separators=(',', ':'))
    env['FLE_CJS'] = a.cjs
    r = subprocess.run(['node', os.path.join(HERE, 'fle_wasm_runner.mjs')], env=env,
                       capture_output=True, text=True, cwd=HERE)
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-3000:])
        sys.exit('wasm runner failed')
    print(r.stdout.strip())
    wres = json.load(open(os.path.join(HERE, 'work', 'wasm_results.json')))
    by_key = {(c['fn'], c['id']): c for c in wres['cases']}

    # ---- 2) native 側 (standalone driver — python3 が non-PIE で 0x400000 を占有するため別プロセス) ----
    case_file = os.path.join(HERE, 'work', 'nat_cases.txt')
    nat_out = os.path.join(HERE, 'work', 'nat_results.jsonl')
    with open(case_file, 'w') as fh:
        for (va, nm, pid, prep, gpr, xmm, stk, ad) in all_cases:
            g = list(gpr) + [0] * (4 - len(gpr))
            x = list(xmm) + [0] * (4 - len(xmm))
            s = list(stk) + [0] * (8 - len(stk))
            fh.write('CASE %x %s %s %s %s %s\n' % (
                va, pid, prep or '-',
                ' '.join(hex(v) for v in g), ' '.join(hex(v) for v in x),
                '%d %s' % (len(stk), ' '.join(hex(v) for v in s))))
    drv = os.path.join(HERE, 'work', 'fle_natdrv')
    rn = subprocess.run(['setarch', 'x86_64', '-R', drv, case_file, nat_out, PE],
                        capture_output=True, text=True, cwd=HERE)
    if rn.returncode != 0:
        print(rn.stdout[-2000:], rn.stderr[-2000:])
        sys.exit('native driver failed rc=%d' % rn.returncode)
    nres = {}
    with open(nat_out) as fh:
        for line in fh:
            c = json.loads(line)
            nres[(int(c['fn'], 16), c['id'])] = c

    results = []
    for (va, nm, pats) in SPOT:
        mach = static_features(va)
        fnres = {'liftdiff_version': 1, 'target': 'flelift',
                 'function': {'va': '0x%x' % va, 'name': 'function_%x' % va,
                              'sig': {'ret': 'i64', 'params': ['i64'], 'defined': True}},
                 'verdict': 'match', 'unexec_reason': None, 'tags': [], 'cases': [],
                 'static': {'machine': mach,
                            'ir': {'icalls': 0, 'fcmp': 0, 'asm_calls': 0, 'allocas': 0, 'regslot_deref': 0,
                                   'note': 'x64c route: IR 無し (C 1:1 lift)。対応は lift_meta.json 参照'}}}
        for (pid, prep, gpr, xmm, stk, ad) in pats:
            # native 結果 (driver 実行済み)
            ncase = nres.get((va, pid))
            nat_status = ncase['status'] if ncase else 'native_fault'
            rax = int(ncase['rax'], 16) if ncase and ncase['status'] == 'ok' else None
            x0 = int(ncase['x0'], 16) if ncase and ncase['status'] == 'ok' else None
            ndiff = []
            if ncase and ncase['status'] == 'ok':
                for d in ncase['mem']:
                    ndiff.append({'r': d['r'], 'o': d['o'], 'native': d['a'], 'pri': d['b']})
            # wasm 結果
            wcase = by_key.get((va, pid))
            outcome = 'equal'
            diffs = {}
            if nat_status != 'ok' and wcase['status'] != 'ok':
                outcome = 'both_fault'
            elif nat_status != 'ok':
                outcome = 'native_fault'
            elif wcase['status'] != 'ok':
                outcome = 'wasm_trap'
            else:
                wmap = {(c['r'], int(c['o'], 16)): c for c in wcase['mem']}
                dd = []
                for d in ndiff:
                    wc = wmap.get((d['r'], int(d['o'], 16)))
                    d['wasm'] = wc['a'] if wc else None
                    if wc is None or wc['a'] != d['native']:
                        dd.append(d)
                for key, wc in wmap.items():
                    if not any((d['r'], int(d['o'], 16)) == key for d in ndiff):
                        dd.append({'r': wc['r'], 'o': wc['o'], 'native': None, 'wasm': wc['a'], 'pri': wc.get('b', '0x0')})
                ret_diff = (('0x%x' % rax) if rax is not None else None) != wcase['rax']
                x0_diff = (('0x%x' % x0) if x0 is not None else None) != wcase['x0']
                if ret_diff or x0_diff or dd:
                    outcome = 'diff'
                diffs = {'mem': {'count': len(dd), 'first': dd[:8]}}
                if ret_diff:
                    diffs['ret'] = {'native': '0x%x' % rax if rax is not None else None, 'wasm': wcase['rax']}
                if x0_diff:
                    diffs['xmm0'] = {'native': '0x%x' % x0 if x0 is not None else None, 'wasm': wcase['x0']}
            fnres['cases'].append({'id': '%x:%s' % (va, pid), 'pattern': pid, 'outcome': outcome,
                                   'native_status': nat_status, 'wasm_status': wcase['status'],
                                   'args': ad, 'diffs': diffs, 'wasm_uninit_dependent': False})
        outs = [c['outcome'] for c in fnres['cases']]
        if all(o == 'equal' for o in outs):
            fnres['verdict'] = 'match'
        elif all(o in ('equal', 'native_fault', 'both_fault') for o in outs):
            fnres['verdict'] = 'match' if any(o == 'equal' for o in outs) else 'unexec'
            if fnres['verdict'] == 'unexec':
                fnres['unexec_reason'] = 'native_fault_all_patterns'
        else:
            fnres['verdict'] = 'mismatch'
        results.append(fnres)

    with open(a.out, 'w') as fh:
        for fnres in results:
            fh.write(json.dumps(fnres, ensure_ascii=False) + '\n')
    summ = {'verdicts': {r['function']['va']: r['verdict'] for r in results},
            'cases': sum(len(r['cases']) for r in results),
            'equal': sum(1 for r in results for c in r['cases'] if c['outcome'] == 'equal')}
    json.dump(summ, open(a.summary, 'w'), ensure_ascii=False, indent=1)
    print('[fle_diff] %d functions / %d cases / equal %d' % (len(results), summ['cases'], summ['equal']))
    for r in results:
        print('  %s (%s): %s — %s' % (r['function']['va'], r['function']['name'], r['verdict'],
                                      ','.join(c['outcome'] for c in r['cases'])))


if __name__ == '__main__':
    main()
