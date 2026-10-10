#!/usr/bin/env python3
"""ldmach.py — capstone による機械語正本の関数単位スキャン (CAB-231 ldfix 用)。

PE (.pdata の RUNTIME_FUNCTION) から関数区間を取り出し、closure (IR の define function_*)
の各関数を線型逆アセンブルして「メモリ操作」を解析する。
アドレス規約 (tools/liftdiff/docs/FORMAT.md と共通): VA = RVA + ImageBase(0x400000)、
RetDec IR の inttoptr 定数は LVA = VA - 0x400000。
"""
import re
import struct
import capstone

BASE = 0x400000

GPR64 = ('rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp',
         'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15')
GPR_SET = set(GPR64)

_REG_ALIAS = {}
for _n in GPR64:
    _REG_ALIAS[_n] = _n
for _p, _q in (('eax', 'rax'), ('ebx', 'rbx'), ('ecx', 'rcx'), ('edx', 'rdx'),
               ('esi', 'rsi'), ('edi', 'rdi'), ('ebp', 'rbp'), ('esp', 'rsp')):
    _REG_ALIAS[_p] = _q
    _REG_ALIAS[_p[1:]] = _q          # ax/bx/... , al/ah/bl/...
for _i in range(8, 16):
    for _s in ('', 'd', 'w', 'b'):
        _REG_ALIAS['r%d%s' % (_i, _s)] = 'r%d' % _i
# ah/bh/ch/dh は親が違うが detag 用の近似として rax..rdx に寄せる (load 幅判定では 8bit は除外するので実害なし)
_REG_ALIAS['ah'] = 'rax'
_REG_ALIAS['bh'] = 'rbx'
_REG_ALIAS['ch'] = 'rcx'
_REG_ALIAS['dh'] = 'rdx'


def norm_reg(cs, rid):
    """capstone reg id → 64bit 親レジスタ名 (.unknown は None)"""
    try:
        n = cs.reg_name(rid)
    except Exception:
        return None
    if not n:
        return None
    return _REG_ALIAS.get(n.lower())


# RMW (read-modify-write) 命令: mem を読んで書く
RMW_MN = {'add', 'sub', 'and', 'or', 'xor', 'inc', 'dec', 'neg', 'not', 'xadd', 'cmpxchg',
          'bts', 'btr', 'btc', 'imul'}
# mem からの純読み
LOAD_MN = {'mov', 'movzx', 'movsx', 'movsxd', 'movslq', 'movzbl', 'movsbl', 'movzwq', 'movswq',
           'movups', 'movupd', 'movdqa', 'movdqu', 'movss', 'movsd', 'movaps', 'movapd',
           'movlps', 'movhps', 'movlpd', 'movhpd', 'cmp', 'test', 'bt',
           'punpcklqdq', 'unpcklpd', 'unpcklps'}
STORE_MN = {'mov', 'movups', 'movupd', 'movdqa', 'movdqu', 'movss', 'movsd', 'movaps', 'movapd',
            'movlps', 'movhps', 'movlpd', 'movhpd'}


class Machine:
    """PE 1 本分。read / .pdata 関数境界 / 関数単位の線型 disasm (キャッシュ付)。"""

    def __init__(self, pe_path):
        import pefile
        self.pef = pefile.PE(pe_path, fast_load=True)
        self.base = self.pef.OPTIONAL_HEADER.ImageBase
        self.text = None
        self.pdata = None
        for s in self.pef.sections:
            nm = s.Name.rstrip(b'\0').decode('latin1')
            if nm == '.text':
                self.text = (s.VirtualAddress, s.get_data())
            elif nm == '.pdata':
                self.pdata = (s.VirtualAddress, s.get_data())
        self.fns = {}          # VA -> (rva, size)
        if self.pdata:
            prva, pdata = self.pdata
            for off in range(0, len(pdata) - 11, 12):
                beg, end, _unw = struct.unpack_from('<III', pdata, off)
                if beg == 0 and end == 0:
                    break
                self.fns[self.base + beg] = (beg, end - beg)
        self.cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.cs.detail = True
        self._cache = {}

    def read(self, rva, n):
        trva, data = self.text
        if trva <= rva < trva + len(data):
            return data[rva - trva:rva - trva + n]
        return b''

    def disasm_fn(self, va):
        """関数 VA を .pdata サイズで線型 disasm → [capstone ins] (境界不明は None)"""
        if va in self._cache:
            return self._cache[va]
        ent = self.fns.get(va)
        if not ent:
            self._cache[va] = None
            return None
        rva, size = ent
        data = self.read(rva, size)
        out = list(self.cs.disasm(data, va))
        self._cache[va] = out
        return out


def memops_of(cs, ins):
    """命令 1 個のメモリオペランド解析 → list[dict] (通常 0 or 1 個)。

    dict: kind=load|store|rmw, size_bits, base(64bit名|None), index, disp,
          rip_rva(rip相対の実効RVA), write
    lea などアドレス計算のみは None。
    """
    mn = ins.mnemonic
    if mn == 'lea' or mn.startswith('set') or mn.startswith('j'):
        return []
    ops = ins.operands
    out = []
    for mi, op in enumerate(ops):
        if op.type != capstone.CS_OP_MEM:
            continue
        if mn in RMW_MN:
            kind = 'rmw'
        elif mn in STORE_MN:
            kind = 'store' if mi == 0 else 'load'
        elif mn in LOAD_MN:
            kind = 'load'
        else:
            kind = 'other'
        d = dict(kind=kind,
                 size_bits=op.size * 8 if op.size else None,
                 base=norm_reg(cs, op.mem.base) if op.mem.base else None,
                 index=norm_reg(cs, op.mem.index) if op.mem.index else None,
                 disp=op.mem.disp,
                 write=(kind in ('store', 'rmw') and mi == 0) or (kind == 'rmw'))
        raw_base = cs.reg_name(op.mem.base) if op.mem.base else None
        if raw_base == 'rip':
            d['rip_rva'] = ins.address + ins.size + op.mem.disp
            d['base'] = None
        out.append(d)
    return out


class FnMach:
    """1 関数分の機械語ビュー: 命令列 + IR ブロック (dec_label_pc_<VA>) 割当。"""

    def __init__(self, mach, va, block_vas):
        self.va = va
        self.cs = mach.cs
        self.ins = mach.disasm_fn(va) or []
        self.block_starts = sorted(block_vas)
        self.blocks = {}       # block_va -> [ins...]
        bvs = self.block_starts
        import bisect
        for ins in self.ins:
            i = bisect.bisect_right(bvs, ins.address)
            blk = bvs[i - 1] if i > 0 else None
            self.blocks.setdefault(blk, []).append(ins)

    def iter_memops(self, block_va=None):
        ins_list = self.ins if block_va is None else self.blocks.get(block_va, [])
        for ins in ins_list:
            for m in memops_of(self.cs, ins):
                m['addr'] = ins.address
                m['mnem'] = ins.mnemonic
                m['ins'] = ins
                yield m

    def has_reg_memop(self, reg, zero_disp=True):
        """reg をベースにしたメモリ操作が関数内にあるか (spill_slot_deref の機械語裏取り)"""
        for m in self.iter_memops():
            if m['base'] == reg and (not zero_disp or m['disp'] == 0):
                return True
        return False
