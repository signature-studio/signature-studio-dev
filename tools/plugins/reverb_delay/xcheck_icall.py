#!/usr/bin/env python3
"""PLG-F4 (#201) 別算法検算: audit_icall.py (recursive descent + jump table 解決) とは独立に、閉包 ranges を capstone の
線形 sweep で逆アセンブルし、非 IAT の間接 call (オペランドが即値でない call; IAT 判定は PE import テーブル) の VA 集合を作って、
audit_icall.py の `--sites` 出力 (mn == call かつ kind != iat) の VA 集合と **VA 単位**で比較する。

合格条件 (どれか違えば exit 1):
  (1) audit にあって線形 sweep に無い site が 0   (audit が実在しない site を数えていない)
  (2) 線形 sweep にだけ有る site の VA 集合 == --expected ファイルの集合 (1 行 1 VA, 16 進)
      既知の 3 site は Delphi `try/finally` の funclet 本体 (直前が `jmp` + nop nop。 CFG の辺から到達せず、recursive descent と RetDec は辿らない)。
      想定外の差 (増えた / 消えた) が出たら不合格にする = 件数ではなく VA で固定した回帰 gate。
usage: xcheck_icall.py [--dir work/reverb_delay/icall] [--expected reverb_delay/icall_linear_only.expected] <block> ...
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

W = os.path.join(HERE, '..', 'work')


def linear_sites(block):
    pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % block), fast_load=True)
    pe.parse_data_directories()
    base = pe.OPTIONAL_HEADER.ImageBase
    iat = {i.address for d in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []) for i in d.imports if i.address}
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    out = set()
    for r in open(os.path.join(W, 'closure', 'block%05d.ranges.txt' % block)).read().replace(',', '\n').split():
        lo, hi = (int(x, 16) for x in r.split('-'))
        for i in md.disasm(pe.get_data(lo - base, hi - lo + 1), lo):
            if i.mnemonic != 'call' or i.operands[0].type == X86_OP_IMM:
                continue
            o = i.operands[0]
            if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP and (i.address + i.size + o.mem.disp) in iat:
                continue
            out.add(i.address)
    return out


def main(argv):
    D = os.path.join(W, 'reverb_delay', 'icall')
    exp_path = os.path.join(HERE, 'icall_linear_only.expected')
    while argv[:1] and argv[0].startswith('--'):
        if argv[0] == '--dir':
            D = argv[1]
        elif argv[0] == '--expected':
            exp_path = argv[1]
        else:
            print('unknown option', argv[0], file=sys.stderr)
            return 2
        argv = argv[2:]
    expected = {int(l.split('#')[0].strip(), 16) for l in open(exp_path) if l.split('#')[0].strip()}
    tot_lin = tot_aud = 0
    seen_lin_only, bad = set(), 0
    for b in map(int, argv):
        lin = linear_sites(b)
        sites = json.load(open(os.path.join(D, '%d.sites.json' % b)))
        aud = {s['va'] for s in sites if s['mn'] == 'call' and s['kind'] != 'iat'}
        n_json = json.load(open(os.path.join(D, '%d.icall.json' % b)))['call_non_iat']
        aud_only, lin_only = aud - lin, lin - aud
        seen_lin_only |= lin_only
        tot_lin += len(lin)
        tot_aud += len(aud)
        ok = not aud_only and len(aud) == n_json
        bad += not ok
        print('%d linear-sweep=%d audit_icall=%d (icall.json call_non_iat=%d) audit-only=%s linear-only=%s %s' % (
            b, len(lin), len(aud), n_json, [hex(a) for a in sorted(aud_only)], [hex(a) for a in sorted(lin_only)], 'OK' if ok else 'NG'))
    unexpected = seen_lin_only - expected
    # expected は今回の block 集合で見えるはずのもの。 消えたら (= audit が到達できるようになった / 閉包が変わった) 不合格
    vanished = expected - seen_lin_only
    if unexpected or vanished:
        bad += 1
        print('NG: linear-only の想定外: 増 %s / 消 %s' % ([hex(a) for a in sorted(unexpected)], [hex(a) for a in sorted(vanished)]))
    print('xcheck_icall: 合計 linear-sweep=%d audit_icall=%d linear-only %d site (expected %d, 一致=%s) %s' % (
        tot_lin, tot_aud, len(seen_lin_only), len(expected), seen_lin_only == expected, 'OK' if not bad else 'NG'))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
