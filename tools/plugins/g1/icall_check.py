#!/usr/bin/env python3
"""閉包の「非 IAT 間接 call」を、機械語 (静的 site) と lift 後 IR (p.final.ll) で比べる (PLG-G1 / #206)。 f2 (#199) §3 と同じ測定。

  python3 icall_check.py [--json-dir DIR] <block> ...
    既定: work/g1/icall/<block>.icall.json を tools/icall/audit_icall.py (--funcs <閉包関数 VA> --ir work/batch/<block>/p.final.ll) で生成。
    --json-dir DIR: 生成せず DIR/<block>.icall.json を読む (ネガティブコントロール用)。
gate (exit 1): 独立算法の線形 sweep (capstone で閉包 ranges を逆アセンブル、オペランドが即値でない call のうち IAT 呼出を除く) の数が、
  audit_icall の `call_non_iat` (recursive descent で到達した site) + `gap_sites` (到達しないが decode できた gap の間接 call/jmp) と一致しない block が 1 つでもある / 入力 JSON 不在。
  (gap を足すのは、audit が到達不能と判定した機械語内の call も sweep は数えるため。 f2 の 11 block では gap 0 で単純な一致だった)
測定のみ (gate ではない): IR の間接 call 数。 静的 site > 0 かつ IR 0 の block は「脱落」と表示する (lift 鎖に icall 復元が無いことの観測)。
"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(P, '..', 'shared'))
sys.path.insert(0, HERE)
from paths import FL_WIN64_DIR
from common import PLUGINS
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

W = os.path.join(P, 'work')
NAMES = {}
for n, sh, _ in PLUGINS:
    if sh is not None:
        NAMES.setdefault(sh, []).append(n)


def sweep(b):
    pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % b), fast_load=True)
    pe.parse_data_directories()
    base = pe.OPTIONAL_HEADER.ImageBase
    iat = {i.address for d in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []) for i in d.imports if i.address}
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    n = 0
    for r in open(os.path.join(W, 'closure', 'block%05d.ranges.txt' % b)).read().replace(',', '\n').split():
        lo, hi = (int(x, 16) for x in r.split('-'))
        for i in md.disasm(pe.get_data(lo - base, hi - lo + 1), lo):
            if i.mnemonic != 'call' or i.operands[0].type == X86_OP_IMM:
                continue
            o = i.operands[0]
            if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP and (i.address + i.size + o.mem.disp) in iat:
                continue
            n += 1
    return n


def audit(b, jdir, generate):
    j = os.path.join(jdir, '%d.icall.json' % b)
    if generate:
        os.makedirs(jdir, exist_ok=True)
        funcs = os.path.join(jdir, '%d.funcs' % b)
        rg = open(os.path.join(W, 'closure', 'block%05d.ranges.txt' % b)).read().replace(',', '\n').split()
        open(funcs, 'w').write('\n'.join(r.split('-')[0] for r in rg) + '\n')
        subprocess.run([sys.executable, os.path.join(P, '..', 'icall', 'audit_icall.py'),
                        '--pe', os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % b),
                        '--ir', os.path.join(W, 'batch', str(b), 'p.final.ll'), '--funcs', funcs, '--json', j, '--label', str(b)],
                       check=True, stdout=subprocess.DEVNULL)
    return json.load(open(j)) if os.path.exists(j) else None


def main():
    a = sys.argv[1:]
    jdir, generate = os.path.join(W, 'g1', 'icall'), True
    if a[:1] == ['--json-dir']:
        jdir, generate, a = a[1], False, a[2:]
    print('| block | plugin | 静的 site (audit_icall 到達) | gap site | 線形 sweep | 一致 | IR の間接 call | 入口スロット 静的→IR (slot=n→m) | 判定 |')
    print('|--:|---|--:|--:|--:|---|--:|---|---|')
    bad = 0
    tot = [0, 0, 0, 0]
    for b in map(int, a):
        try:
            j = audit(b, jdir, generate)
        except Exception as e:
            print('FAIL: audit_icall 失敗 %d: %s' % (b, e), file=sys.stderr)
            bad += 1
            continue
        if j is None:
            print('FAIL: %s/%d.icall.json が無い' % (jdir, b), file=sys.stderr)
            bad += 1
            continue
        sw = sweep(b)
        c = json.load(open(os.path.join(W, 'closure', 'block%05d.json' % b)))
        cmp_ = {r['fn']: r for r in j['per_fn_cmp']}
        ent, ent_ir = [], 0
        for slot, va in c['entries'].items():
            r = cmp_.get(va)
            if r and r['static_call_ind']:
                ent.append('%s=%d→%d' % (slot, r['static_call_ind'], r['ir_call_ind']))
                ent_ir += r['ir_call_ind']
        gap = j.get('gap_sites', 0)
        eq = sw == j['call_non_iat'] + gap
        bad += not eq
        tot[0] += j['call_non_iat']; tot[1] += gap; tot[2] += sw; tot[3] += j['ir_call_ind_total']
        verdict = 'MISMATCH' if not eq else ('脱落 (静的>0・IR 0)' if j['call_non_iat'] > 0 and j['ir_call_ind_total'] == 0 else
                                           ('一部残存' if j['call_non_iat'] > 0 else '間接 call なし'))
        print('| %d | %s | %d | %d | %d | %s | %d | %s | %s |' % (b, ' / '.join(NAMES.get(b, ['?'])), j['call_non_iat'], gap, sw,
                                                          'EQ' if eq else 'DIFF', j['ir_call_ind_total'], ', '.join(ent) or '-', verdict))
    print('| 合計 | | %d | %d | %d | | %d | | |' % tuple(tot))
    print('icall_check: sweep ≠ audit 到達 + gap の block = %d' % bad)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
