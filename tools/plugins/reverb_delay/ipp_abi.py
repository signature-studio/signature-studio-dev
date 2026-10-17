#!/usr/bin/env python3
"""T3 Multiband Delay engine (19165) の IPPCODE 入口の ABI を静的に同定する (#4497 / #3445 PLG-F4-3 §5)。

測定のみ (判定はしない・実行はしない)。 pefile + capstone。 Windows x64 呼出規約を仮定する。
対象: ipp_callers.py の P 基準で `.text` の pdata 関数から直接 call される IPPCODE 入口 (text 区分)。
各入口について:
  reads   本体の先頭 (ret までの pdata 関数全体) で、引数レジスタ (rcx rdx r8 r9 xmm0-3) を書き込み前に読んだ数
  sets    各呼出元で、call の直前 WINDOW 命令以内に設定された引数レジスタ数 (呼出元ごと・最小 / 最大)
  isa     本体の命令セット: x87 (f*)・SSE スカラ/パック・AVX (v*) の有無
  calls   本体から直接 call する先の数 (IPPCODE 内 / 外)
出力: 入口ごとの表 (JSON) と、区分ごとの件数。
usage: ipp_abi.py [--json OUT]
"""
import collections, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ipp_callers as ic
from capstone.x86 import X86_OP_IMM
from capstone import CS_ARCH_X86, CS_MODE_64, Cs

WINDOW = 12


PURE_WRITE = {'mov', 'movsxd', 'movzx', 'movsx', 'lea', 'movsd', 'movss', 'movaps', 'movups', 'movapd',
              'movupd', 'movdqa', 'movdqu', 'movq', 'movd', 'movlps', 'movhps', 'movlpd', 'movhpd'}
ALIAS = {}
for _full, _subs in (('rcx', ('ecx', 'cx', 'cl')), ('rdx', ('edx', 'dx', 'dl')),
                     ('r8', ('r8d', 'r8w', 'r8b')), ('r9', ('r9d', 'r9w', 'r9b'))):
    for _s in _subs:
        ALIAS[_s] = _full
    ALIAS[_full] = _full
for _x in ('xmm0', 'xmm1', 'xmm2', 'xmm3'):
    ALIAS[_x] = _x
ARG_NAMES = {'rcx': 0, 'rdx': 1, 'r8': 2, 'r9': 3, 'xmm0': 'x0', 'xmm1': 'x1', 'xmm2': 'x2', 'xmm3': 'x3'}


def rw(ins):
    """オペランドから (読んだ正規化レジスタ, 書いた正規化レジスタ) を求める。 capstone の暗黙 regs は使わない。"""
    from capstone.x86 import X86_OP_REG, X86_OP_MEM
    reads, writes = set(), set()
    ops = ins.operands
    for k, op in enumerate(ops):
        if op.type == X86_OP_MEM:
            for r in (op.mem.base, op.mem.index):
                if r:
                    n = ALIAS.get(ins.reg_name(r))
                    if n:
                        reads.add(n)
        elif op.type == X86_OP_REG:
            n = ALIAS.get(ins.reg_name(op.reg))
            if n is None:
                continue
            if k == 0 and ins.mnemonic in PURE_WRITE:
                writes.add(n)
            elif k == 0 and ins.mnemonic in ('xor', 'sub') and len(ops) == 2 and ops[1].type == X86_OP_REG and ops[1].reg == op.reg:
                writes.add(n)
            elif k == 0 and ins.mnemonic not in ('cmp', 'test', 'bt', 'ucomisd', 'ucomiss', 'comisd', 'comiss'):
                reads.add(n)
                writes.add(n)
            else:
                reads.add(n)
    if ins.mnemonic in ('cmp', 'test', 'ucomisd', 'ucomiss', 'comisd', 'comiss') and ops:
        for op in ops:
            if op.type == X86_OP_REG and ALIAS.get(ins.reg_name(op.reg)):
                reads.add(ALIAS[ins.reg_name(op.reg)])
    return reads, writes


def callee_reads(body):
    """本体 (pdata 関数の先頭から最初の ret まで) で、引数レジスタを書き込み前に読んだ集合。"""
    written, read = set(), set()
    for ins in body:
        rd, wr = rw(ins)
        for n in rd:
            if n in ARG_NAMES and n not in written:
                read.add(ARG_NAMES[n])
        written |= wr
        if ins.mnemonic == 'ret':
            break
    return sorted(read, key=str)


def caller_sets(seq, idx):
    """seq[idx] が call のとき、直前 WINDOW 命令で設定された引数レジスタの集合 (call/jmp/ret で打ち切る) を返す。"""
    got = set()
    for j in range(max(0, idx - WINDOW), idx):
        ins = seq[j]
        if ins.mnemonic in ('call', 'jmp', 'ret') or ins.mnemonic.startswith('j'):
            got.clear()
            continue
        _, wr = rw(ins)
        for n in wr:
            if n in ARG_NAMES:
                got.add(ARG_NAMES[n])
    return got


def isa_of(body):
    f = s = v = 0
    for ins in body:
        m = ins.mnemonic
        if m.startswith('f') and m not in ('fwait',):
            f += 1
        elif m.startswith('v') and m not in ('vzeroupper',):
            v += 1
        elif m.endswith('ps') or m.endswith('ss') or m.endswith('sd') or m.endswith('pd'):
            s += 1
    return {'x87': f, 'sse': s, 'avx': v}


def main():
    out_json = None
    if '--json' in sys.argv:
        out_json = sys.argv[sys.argv.index('--json') + 1]
    pe = ic.pefile.PE(ic.path(ic.ENGINE), fast_load=True)
    pe.parse_data_directories(directories=[ic.pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = {s.Name.rstrip(b'\0').decode(errors='replace'): s for s in pe.sections}
    ipp = secs['IPPCODE']
    lo, hi = base + ipp.VirtualAddress, base + ipp.VirtualAddress + ipp.Misc_VirtualSize
    import struct
    pdata = secs['.pdata'].get_data()
    funcs = set()
    for i in range(len(pdata) // 12):
        s, e, u = struct.unpack_from('<III', pdata, 12 * i)
        if s and e > s and not (u & 1):
            funcs.add((base + s, base + e))
    funcs = sorted(funcs)
    fstart = {a: e for a, e in funcs}
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    ipp_entries = {a for a, _ in funcs if lo <= a < hi}
    # 直接 call 元 (.text pdata 関数) と、その呼出し箇所の直前列
    callers = collections.defaultdict(list)
    for a, e in funcs:
        if lo <= a < hi:
            continue
        seq = list(md.disasm(pe.get_data(a - base, e - a), a))
        for k, ins in enumerate(seq):
            if ins.mnemonic == 'call' and ins.operands and ins.operands[0].type == X86_OP_IMM:
                t = ins.operands[0].imm
                if t in ipp_entries:
                    callers[t].append((a, caller_sets(seq, k)))
    rows = []
    kinds = collections.Counter()
    for t in sorted(callers):
        e = fstart[t]
        body = list(md.disasm(pe.get_data(t - base, e - t), t))
        reads = callee_reads(body)
        sets = [len(s) for _, s in callers[t]]
        isa = isa_of(body)
        calls_ipp = sum(1 for ins in body if ins.mnemonic == 'call' and ins.operands and ins.operands[0].type == X86_OP_IMM and lo <= ins.operands[0].imm < hi)
        calls_out = sum(1 for ins in body if ins.mnemonic == 'call' and ins.operands and ins.operands[0].type != X86_OP_IMM)
        row = {'va': hex(t), 'size': e - t, 'insns': len(body), 'callers': len(callers[t]),
               'reads': [str(r) for r in reads], 'set_min': min(sets), 'set_max': max(sets),
               'isa': isa, 'calls_ipp': calls_ipp, 'calls_indirect_or_rip': calls_out}
        rows.append(row)
        kinds[(len(reads), min(sets), max(sets))] += 1
    summary = {'entries_text_direct': len(rows), 'by_reads_sets': {str(k): v for k, v in sorted(kinds.items())}}
    if out_json:
        with open(out_json, 'w') as f:
            json.dump({'summary': summary, 'rows': rows}, f, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
