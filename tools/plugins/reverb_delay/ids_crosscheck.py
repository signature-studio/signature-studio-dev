#!/usr/bin/env python3
"""closure_facts.py (host_calls.py の taint 追跡) の Dispatcher ID を別アルゴリズムで検算する。
taint を使わず、閉包 ranges を線形逆アセンブルして「`mov r8d, imm` / `xor r8d, r8d` の後 8 命令以内にある
`call qword ptr [reg]` (disp 0, index 無し, base が rip でない)」を全数拾う。 host 以外の vtable slot0 呼出も拾うため上位集合になる。

usage: ids_crosscheck.py [--facts work/reverb_delay/facts.json]
前提: reverb_delay_e2e.sh 実行済み + `source reverb_delay/env.sh`。
不合格 (exit 1) の条件 — どれか 1 つでも該当:
  (1) taint 版の即値 ID の site 数が、本走査の同 ID の site 数を超える (= 本走査が taint 版を再現できない)
  (2) taint 版の即値 ID が framework/hostshim/hs_ids.json の ID 集合に無い (= P0b の応答表で覆えない)
  (3) facts.json の plugin に対応する closure json / PE が読めない (検算が走らない状態を合格にしない)
本走査だけが見つけた ID (taint 版に無い) は情報として表示する (host 以外の slot0 呼出を含みうる)。
"""
import os, sys, json, collections
HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(P, '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG


def scan_ids(pe, ranges):
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    base = pe.OPTIONAL_HEADER.ImageBase
    found = collections.Counter()
    for r in ranges:
        a, b = (int(x, 16) for x in r.split('-'))
        code = pe.get_data(a - base, b - a + 1)
        r8, age = None, 99
        for ins in md.disasm(code, a):
            age += 1
            if ins.mnemonic == 'call':
                op = ins.operands[0]
                if op.type == X86_OP_MEM and op.mem.disp == 0 and op.mem.index == 0 and ins.reg_name(op.mem.base) not in ('rip', ''):
                    found['dyn' if (r8 is None or age > 8) else r8] += 1
                r8 = None
                continue
            if len(ins.operands) == 2 and ins.operands[0].type == X86_OP_REG and ins.reg_name(ins.operands[0].reg) == 'r8d':
                if ins.mnemonic == 'mov' and ins.operands[1].type == X86_OP_IMM:
                    r8, age = ins.operands[1].imm, 0
                elif ins.mnemonic == 'xor' and ins.operands[1].type == X86_OP_REG and ins.reg_name(ins.operands[1].reg) == 'r8d':
                    r8, age = 0, 0
                else:
                    r8 = None
    return found


def main(argv):
    facts = os.path.join(P, 'work', 'reverb_delay', 'facts.json')
    if '--facts' in argv:
        facts = argv[argv.index('--facts') + 1]
    F = json.load(open(facts))
    hs = {int(k) for k in json.load(open(os.path.join(P, 'framework', 'hostshim', 'hs_ids.json')))['ids']}
    bad = 0
    for name, f in F.items():
        blk = f['block']
        reasons = []
        try:
            c = json.load(open(os.path.join(P, 'work', 'closure', 'block%05d.json' % blk)))
            pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % blk), fast_load=True)
            found = scan_ids(pe, c['ranges'])
        except (OSError, KeyError, ValueError) as e:
            bad += 1
            print('%-20s NG (検算が走らない: %s)' % (name, e))
            continue
        taint = {int(k): v for k, v in f['host']['ids'].items() if k != 'dyn'}
        for k, v in taint.items():
            if found.get(k, 0) < v:
                reasons.append('ID %d: taint %d site > 独立走査 %d site' % (k, v, found.get(k, 0)))
            if k not in hs:
                reasons.append('ID %d: hs_ids.json に無い' % k)
        only = {str(k): v for k, v in sorted(found.items(), key=lambda x: str(x[0])) if k != 'dyn' and k not in taint}
        bad += bool(reasons)
        print('%-20s taint(imm ID: site)=%s  独立走査(imm ID: site)=%s  %s%s' % (
            name, {str(k): v for k, v in sorted(taint.items())},
            {str(k): v for k, v in sorted(found.items(), key=lambda x: str(x[0])) if k != 'dyn'},
            'OK' if not reasons else 'NG ' + '; '.join(reasons),
            ('  [独立走査のみの ID: %s]' % only) if only else ''))
    print('ids_crosscheck: %d/%d プラグインで合格 (取りこぼしなし かつ hs_ids.json に被覆)' % (len(F) - bad, len(F)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
