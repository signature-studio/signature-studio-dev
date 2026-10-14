#!/usr/bin/env python3
"""PLG-F2 (#514): icall_gate_waivers.json の 18979 0x741035 waiver を機械検証する。

waiver の主張「0x741035 を含む基本ブロック B は通常制御フローから到達不能で、RetDec が基本ブロックごと除去した」を、
手作業の追跡 (evidence 欄) ではなく次の 5 検査で確かめる。どれか失敗で exit 1。

  V1 0x741035 を含む関数 (.pdata) の開始 VA が 0x740e30
  V2 B = 0x741007 (0x741035 の直前の無条件終端 jmp の次の命令) へ入る参照は PE 全体で 1 件 (0x740f28 の jmp)。
     参照 = 直接 jmp/jcc/call の target・即値・rip 相対の計算先、加えてデータ中の絶対 VA (8 byte) と RVA (4 byte)
  V3 0x740e30 の関数内に間接 jmp が無い (jump table からの入口が無い)
  V4 引数 v の格納先 [rbp+0x40] への書込みは入口 0x740e46 の 1 件だけ、その address を取る lea が無く、
     rbp/rsp は prologue/epilogue 以外で書き換わらない (呼出し先から v が書換わらない前提)
  V5 関数入口 0x740e6a から 0x740f28 (= B へ入る jmp) までの経路を v の全域について評価し、0x740f28 に到達する v が 0 件。
     評価は decode 結果を解釈する (mov で eax に v を載せ、cmp/test/sub/jcc/jmp を追う)。eax や flags を追えない
     分岐 (例: [rbp+0x48] 依存の test) は両方向を試す (過大近似)。
     `--domain window` (既定): 境界の代表 |v|<=1024 と両端 2^31 付近 1024 件。経路の定数は全て |c|<512 なので、
       比較の境界は定数の近傍と符号境界 (±2^31) の近傍にしか存在せず、この窓で区間の全域を覆う。
     `--domain full`: int32 全 2^32 値 (chunk 処理、一回限りの全数検査)。
  非空振り: 0x7411dd (jae が成立する経路) に到達する v が 1 以上 (評価器が分岐を実際に辿れていることの確認)。

使い方: python3 tools/plugins/f2/waiver_proof.py [--pe PE] [--domain window|full] [--json OUT]
既定の PE は FL_WIN64_DIR/extracted/block18979_PE.bin。
"""
import argparse, json, os, struct, sys

import numpy as np
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import (X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_EAX, X86_REG_RAX, X86_REG_AX, X86_REG_AL,
                          X86_REG_RBP, X86_REG_RIP)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR

BLOCK = 18979
FUNC = 0x740e30          # waiver.function
SITE = 0x741035          # waiver.site (call qword ptr [rdi+0x1f0])
ENTRY = 0x740e6a         # cmp の起点 (mov eax,[rbp+0x40] の位置)
P = 0x740f28             # jmp 0x741007 (B への唯一の直接参照として期待する命令)
V_STORE = 0x740e46       # mov dword ptr [rbp+0x40], edx (引数 v の唯一の書込み)
OUT_JAE = 0x7411dd       # jae 0x7411dd の成立先
FRAME_OFF = 0x40
ALLOWED_RBP_WRITE = {0x740e30, 0x740e36, 0x740e3a, 0x7413c2, 0x7413ce}  # push rbp / add rsp / mov rbp,rsp / lea rsp / pop rbp
EAX_FAMILY = (X86_REG_EAX, X86_REG_RAX, X86_REG_AX, X86_REG_AL)
STOPS = (P, OUT_JAE)


def load(pe_path):
    pe = pefile.PE(pe_path, fast_load=True)
    data = open(pe_path, 'rb').read()
    base = pe.OPTIONAL_HEADER.ImageBase
    text = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
    pdata = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
    pd = data[pdata.PointerToRawData: pdata.PointerToRawData + pdata.Misc_VirtualSize]
    funcs = []
    for i in range(0, len(pd) - 11, 12):
        b, e, _ = struct.unpack_from('<III', pd, i)
        funcs.append((base + b, base + e))
    return pe, data, base, text, funcs


def code_bytes(data, base, text, lo, hi):
    off = text.PointerToRawData + (lo - base - text.VirtualAddress)
    return data[off: off + (hi - lo)]


def is_eax_dest(ins):
    o = ins.operands
    return len(o) >= 1 and o[0].type == X86_OP_REG and o[0].reg in EAX_FAMILY


def jcc_cond(mn, flags, eax):
    """条件の真偽配列 (uint32 域の v に対する bool 配列)。 追えなければ None (両方向を試す)"""
    if flags is None or eax is None:
        return None
    kind, imm = flags
    imm32 = imm & 0xFFFFFFFF
    simm = imm32 - (1 << 32) if imm32 >= (1 << 31) else imm32
    if kind == 'cmp':
        a = eax
        sa = a.view(np.int32)
        b = np.uint32(imm32)
        sb = np.int32(simm)
        table = {'je': a == b, 'jz': a == b, 'jne': a != b, 'jnz': a != b,
                 'jg': sa > sb, 'jnle': sa > sb, 'jge': sa >= sb, 'jnl': sa >= sb,
                 'jl': sa < sb, 'jnge': sa < sb, 'jle': sa <= sb, 'jng': sa <= sb,
                 'ja': a > b, 'jnbe': a > b, 'jae': a >= b, 'jnb': a >= b, 'jnc': a >= b,
                 'jb': a < b, 'jc': a < b, 'jnae': a < b, 'jbe': a <= b, 'jna': a <= b}
    else:
        zf = (eax & np.uint32(imm32)) == 0
        table = {'je': zf, 'jz': zf, 'jne': ~zf, 'jnz': ~zf}
    return table.get(mn)


def evaluate(v_u, ins_by_addr):
    """v_u: 引数 v の bit pattern (uint32 配列)。 返り値: {stop VA: 到達した v の bool 配列}"""
    reached = {s: np.zeros(v_u.shape, bool) for s in STOPS}
    stack = [(ENTRY, None, None, np.ones(v_u.shape, bool))]
    steps = 0
    while stack:
        addr, eax, flags, mask = stack.pop()
        while True:
            steps += 1
            if steps > 100000:
                raise RuntimeError('evaluate: step limit')
            if addr in STOPS:
                reached[addr] |= mask
                break
            ins = ins_by_addr.get(addr)
            if ins is None:
                break
            mn, o, nxt = ins.mnemonic, ins.operands, addr + ins.size
            if mn == 'mov' and is_eax_dest(ins):
                if o[1].type == X86_OP_MEM and o[1].mem.base == X86_REG_RBP and o[1].mem.disp == FRAME_OFF:
                    eax = v_u
                else:
                    eax = None
                flags = None
            elif mn == 'sub' and is_eax_dest(ins) and o[1].type == X86_OP_IMM:
                eax = None if eax is None else eax - np.uint32(o[1].imm & 0xFFFFFFFF)
                flags = None
            elif mn == 'cmp' and is_eax_dest(ins) and o[1].type == X86_OP_IMM:
                flags = ('cmp', o[1].imm)
            elif mn == 'test' and is_eax_dest(ins) and o[1].type == X86_OP_REG and o[1].reg in EAX_FAMILY:
                flags = ('test', 0xFFFFFFFF)
            elif mn == 'test' and is_eax_dest(ins) and o[1].type == X86_OP_IMM:
                flags = ('test', o[1].imm)
            elif mn == 'jmp':
                if o[0].type != X86_OP_IMM:
                    raise RuntimeError('indirect jmp in evaluated path at %x' % addr)
                addr = o[0].imm
                flags = None
                continue
            elif mn == 'ret':
                break
            elif mn.startswith('j'):
                cond = jcc_cond(mn, flags, eax)
                tgt = o[0].imm
                if cond is None:
                    stack.append((tgt, eax, None, mask))
                else:
                    if (mask & cond).any():
                        stack.append((tgt, eax, None, mask & cond))
                    mask = mask & ~cond
                    if not mask.any():
                        break
                addr = nxt
                continue
            elif mn == 'call':
                eax = None
                flags = None
            else:
                if o and is_eax_dest(ins):
                    eax = None
                flags = None
            addr = nxt
    return reached


def window_domain():
    w = 1024
    lo = np.arange(-w, w, dtype=np.int64)
    edge_lo = np.arange(-(1 << 31), -(1 << 31) + w, dtype=np.int64)
    edge_hi = np.arange((1 << 31) - w, 1 << 31, dtype=np.int64)
    return np.concatenate([lo, edge_lo, edge_hi]) & 0xFFFFFFFF


def run_v5(ins_by_addr, domain):
    total = {s: 0 for s in STOPS}
    if domain == 'window':
        r = evaluate(window_domain().astype(np.uint32), ins_by_addr)
        for s in STOPS:
            total[s] = int(r[s].sum())
        n = window_domain().size
    else:
        n = 1 << 32
        chunk = 1 << 24
        for start in range(0, n, chunk):
            v = (np.arange(start, start + chunk, dtype=np.uint64) & 0xFFFFFFFF).astype(np.uint32)
            r = evaluate(v, ins_by_addr)
            for s in STOPS:
                total[s] += int(r[s].sum())
    return n, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pe', default=os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % BLOCK))
    ap.add_argument('--domain', choices=['window', 'full'], default='window')
    ap.add_argument('--json')
    a = ap.parse_args()

    pe, data, base, text, funcs = load(a.pe)
    tva = base + text.VirtualAddress
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    checks = []

    def check(name, ok, detail):
        checks.append({'check': name, 'pass': bool(ok), 'detail': detail})

    own = [(b, e) for (b, e) in funcs if b <= SITE < e]
    fb, fe = own[0] if own else (None, None)
    check('V1 site の所属関数 == 0x740e30', fb == FUNC, 'site 0x%x は関数 [0x%x,0x%x)' % (SITE, fb or 0, fe or 0))

    fins = list(md.disasm(code_bytes(data, base, text, FUNC, fe), FUNC))
    ins_by_addr = {i.address: i for i in fins}

    site_ins = ins_by_addr[SITE]
    site_end = SITE + site_ins.size
    idx_site = next(k for k, i in enumerate(fins) if i.address == SITE)
    k = idx_site - 1
    while k >= 0 and not (fins[k].mnemonic in ('jmp', 'ret')):
        k -= 1
    B = fins[k + 1].address
    term = fins[k]
    check('B の確定 (site 直前の無条件 jmp の次の命令)', term.mnemonic == 'jmp' and B == 0x741007,
          'B=0x%x, 直前の終端 0x%x %s %s' % (B, term.address, term.mnemonic, term.op_str))
    inner_term = [i.address for i in fins if B <= i.address < SITE and (i.mnemonic.startswith('j') or i.mnemonic == 'ret')]
    check('B (0x%x..0x%x) 内に終端命令なし' % (B, SITE), not inner_term, '終端 %s' % ['0x%x' % x for x in inner_term])

    refs = []
    for (b, e) in funcs:
        if not (tva <= b < tva + text.Misc_VirtualSize):
            continue
        for i in md.disasm(code_bytes(data, base, text, b, e), b):
            for o in i.operands:
                if o.type == X86_OP_IMM and B <= (o.imm & 0xFFFFFFFFFFFFFFFF) < site_end:
                    refs.append((i.address, i.mnemonic, 'imm'))
                if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP:
                    t = i.address + i.size + o.mem.disp
                    if B <= t < site_end:
                        refs.append((i.address, i.mnemonic, 'rip'))
    data_refs = []
    for va in range(B, site_end):
        for kind, pat in (('abs8', struct.pack('<Q', va)), ('rva4', struct.pack('<I', va - base))):
            j = data.find(pat)
            while j != -1:
                data_refs.append((kind, hex(j))); j = data.find(pat, j + 1)
    code_refs = sorted({r[0] for r in refs})
    check('V2 B への参照は 0x740f28 の 1 件 (コード参照 + データ参照)',
          code_refs == [P] and not data_refs,
          'コード参照 %s, データ参照 %s' % (['0x%x %s %s' % (x[0], x[1], x[2]) for x in refs], data_refs))

    ind = [i for i in fins if i.mnemonic == 'jmp' and i.operands[0].type != X86_OP_IMM]
    check('V3 関数内の間接 jmp 0 件', not ind, '間接 jmp %d 件 %s' % (len(ind), ['0x%x %s' % (i.address, i.op_str) for i in ind]))

    writes, escapes, rbp_bad = [], [], []
    for i in fins:
        o = i.operands
        if o and o[0].type == X86_OP_MEM and o[0].mem.base == X86_REG_RBP and o[0].mem.disp == FRAME_OFF:
            writes.append(i.address)
        for x in o:
            if x.type == X86_OP_MEM and x.mem.base == X86_REG_RBP and x.mem.disp == FRAME_OFF and i.mnemonic == 'lea':
                escapes.append(i.address)
        if o and o[0].type == X86_OP_REG and o[0].reg in (X86_REG_RBP,) and i.address not in ALLOWED_RBP_WRITE:
            rbp_bad.append(i.address)
    check('V4 [rbp+0x40] の書込みは入口 0x740e46 の 1 件・取得 (lea) 0 件・rbp 不変',
          writes == [V_STORE] and not escapes and not rbp_bad,
          '書込み %s, lea %s, rbp 書換え(prologue 外) %s' % (['0x%x' % w for w in writes], ['0x%x' % e for e in escapes],
                                                        ['0x%x' % r for r in rbp_bad]))

    n, total = run_v5(ins_by_addr, a.domain)
    check('V5 経路 0x740e6a→0x740f28 で 0x740f28/B に到達する v は 0 件 (domain=%s, %d 値)' % (a.domain, n),
          total[P] == 0,
          'reach P=%d, reach 0x7411dd(jae 成立・過大近似を含む)=%d' % (total[P], total[OUT_JAE]))
    check('V5 非空振り: 0x7411dd に到達する v が 1 以上',
          total[OUT_JAE] > 0, 'reach 0x7411dd=%d' % total[OUT_JAE])

    for c in checks:
        print('%-4s %s | %s' % ('PASS' if c['pass'] else 'FAIL', c['check'], c['detail']))
    ok = all(c['pass'] for c in checks)
    print('RESULT %s (block %d site 0x%x)' % ('PASS' if ok else 'FAIL', BLOCK, SITE))
    if a.json:
        json.dump({'block': BLOCK, 'site': hex(SITE), 'domain': a.domain, 'checks': checks, 'pass': ok}, open(a.json, 'w'), indent=1)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
