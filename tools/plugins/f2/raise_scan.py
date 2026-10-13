#!/usr/bin/env python3
"""#529: icall waiver (icall_gate_waivers.json) の前提「DSP 経路に例外を投げる箇所が無い」の機械的な一次スキャン。

  閉包 ranges の全命令 (線形 sweep) について次を集計する:
    iat    = `call/jmp [rip+IAT]` の import 名 (例外を投げ得る Win32 API・RTL の名前を強調)
    trap   = 0 除算などで例外を起こし得る命令 (div/idiv) と int/int3/ud2
    direct = 閉包外 (frontier / 閉包に無い) への直接 call/jmp 件数 (閉包の BFS 後に残るもの)
  結果は work/f2/raise_scan_<block>.json に出し、標準出力に要約する。
  注: `call [rip+disp]` の target が import 表に無い slot (vtable 様の間接参照) は iat_calls に入らない (閉包の
  call 件数 2 件はこの型で、iat_kinds=0 がその結果)。Win32 IAT 呼出しの有無はこの集計で判定できる。
  これは一次スキャンであり、例外が「無い」ことの証明ではない: frontier (共有 lib) 内の送出、
  メモリ違反 (AV) による SEH 経由の unwind、閉包の間接 call 先は対象外。対象外の扱いは REPORT に明記する。

使い方: python3 tools/plugins/f2/raise_scan.py <block> ...
"""
import json, os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

W = os.path.join(HERE, '..', 'work')
RAISE_NAMES = ('RaiseException', 'RtlRaiseException', 'CxxThrowException', 'abort', 'exit', 'ExitProcess',
               'TerminateProcess', 'RaiseFloatException', 'SetUnhandledExceptionFilter')
TRAP = ('div', 'idiv', 'int', 'int3', 'ud2', 'into')


def scan(block):
    pe_path = os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % block)
    ranges = [tuple(int(x, 16) for x in r.split('-')) for r in
              open(os.path.join(W, 'closure', 'block%05d.ranges.txt' % block)).read().replace(',', '\n').split() if r]
    pe = pefile.PE(pe_path, fast_load=True)
    pe.parse_data_directories()
    base = pe.OPTIONAL_HEADER.ImageBase
    iat = {}
    for d in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        for i in d.imports:
            if i.address:
                iat[i.address] = (d.dll.decode(errors='replace'), (i.name or b'?').decode(errors='replace'))
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    iat_calls = collections.Counter()
    raise_hits = []
    traps = []
    direct_calls = set()
    inside = lambda t: any(lo <= t <= hi for lo, hi in ranges)
    for lo, hi in ranges:
        for i in md.disasm(pe.get_data(lo - base, hi - lo + 1), lo):
            if i.mnemonic in TRAP:
                traps.append([hex(i.address), i.mnemonic, i.op_str])
            if i.mnemonic in ('call', 'jmp') and i.operands and i.operands[0].type == X86_OP_IMM:
                t = i.operands[0].imm
                if not inside(t):
                    direct_calls.add(t)
            if i.mnemonic in ('call', 'jmp') and i.operands and i.operands[0].type == X86_OP_MEM:
                o = i.operands[0]
                if o.mem.base == X86_REG_RIP:
                    tgt = i.address + i.size + o.mem.disp
                    if tgt in iat:
                        dll, name = iat[tgt]
                        iat_calls['%s!%s' % (dll, name)] += 1
                        if any(k in name for k in RAISE_NAMES):
                            raise_hits.append([hex(i.address), dll, name])
    return {'block': block, 'ranges': len(ranges), 'iat_calls': dict(iat_calls), 'raise_api_calls': raise_hits,
            'trap_insns': traps, 'direct_out_of_closure': sorted(hex(t) for t in direct_calls)}


def main():
    os.makedirs(os.path.join(W, 'f2'), exist_ok=True)
    for b in sys.argv[1:]:
        r = scan(int(b))
        json.dump(r, open(os.path.join(W, 'f2', 'raise_scan_%s.json' % b), 'w'), ensure_ascii=False, indent=1)
        print('block %s: ranges=%d iat_kinds=%d raise_api=%d trap=%d direct_out=%d' % (
            b, r['ranges'], len(r['iat_calls']), len(r['raise_api_calls']), len(r['trap_insns']),
            len(r['direct_out_of_closure'])))


if __name__ == '__main__':
    main()
