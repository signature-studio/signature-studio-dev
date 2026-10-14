#!/usr/bin/env python3
"""set_other 台帳の非 imm 349 件 (reg 123・mem 150・lea 76 / #3134 / M11-N171) の接続判定.

台帳 (m11_argrecover.py の site_detail[].src != 'imm') の各引数について、call 直前から後ろ向きに、
その引数を書く定義 (レジスタ族 / [rsp+disp] スロット) を機械語で探し、定義の種類で 3 区分に分ける。
IR は変更しない (分類のみ)。

  実値化   : 直線区間内で全幅の定数に到達 (mov r32/r64, imm・xor r,r・mov qword [rsp+d], imm)。値を記録する。
             reg 由来の mov r,r は元の定義まで追う (copy)。
  復元不能 : 呼出し越えで揮発族 (rax/rcx/rdx/r8/r9/r10/r11/xmm0-5) か引数領域が壊れ、
             Win64 ABI 上その値が call 後に保証されない (call_clobber)。
  未決     : 上記以外。理由ごとに「IR 側で何を接続すれば決まるか」が決まる:
             merge (分岐先越え: CFG 到達定義) / entry (関数入口: 呼出元 def = #1373) /
             call_ret (callee の戻り値) / load_{global,stack,ptr} (メモリ読込) /
             lea_{global,stack,ptr} (アドレス) / arith (算術) / ext (符号・零拡張) /
             partial_* (8/16bit 部分書込・旧値依存) / stack_narrow (型幅未確認の狭いスロット書込) /
             branch (ret/jmp) / other:<mn>
             chain>X: 符号・零拡張 (movzx/movsx/movsxd reg)・即値の加減論理演算 (add/sub/and/or r32|r64, imm) の
             旧値をたどった先の終端 X が未決 (復元不能なら復元不能)

使い方: python3 m11_setother_nonimm_class.py FIXES.json --pe PE
出力: 区分別件数 (stdout)、全行を nonimm_class_rows.json に FIXES.json と同じ dir へ書く。
"""
import argparse, collections, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'ldfix'))
sys.path.insert(0, HERE)
import capstone
import ldmach
import m11_argrecover as AR

ap = argparse.ArgumentParser()
ap.add_argument('fixes'); ap.add_argument('--pe', required=True)
a = ap.parse_args()
d = json.load(open(a.fixes))
mach = ldmach.Machine(a.pe)
fc = {}
M64 = (1 << 64) - 1
VOLATILE = {'rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'} | {'xmm%d' % i for i in range(6)}
GPR = {}
for fam, names in (('rax', ('rax', 'eax', 'ax', 'al', 'ah')), ('rbx', ('rbx', 'ebx', 'bx', 'bl', 'bh')),
                   ('rcx', ('rcx', 'ecx', 'cx', 'cl', 'ch')), ('rdx', ('rdx', 'edx', 'dx', 'dl', 'dh')),
                   ('rsi', ('rsi', 'esi', 'si', 'sil')), ('rdi', ('rdi', 'edi', 'di', 'dil')),
                   ('rbp', ('rbp', 'ebp', 'bp', 'bpl')), ('rsp', ('rsp', 'esp', 'sp', 'spl'))):
    for nm, w in zip(names, (64, 32, 16, 8, 8)):
        GPR[nm] = (fam, w)
for n in range(8, 16):
    for suf, w in (('', 64), ('d', 32), ('w', 16), ('b', 8)):
        GPR['r%d%s' % (n, suf)] = ('r%d' % n, w)
SIZE = {'byte': 8, 'word': 16, 'dword': 32, 'qword': 64}
IMM = re.compile(r'-?(0x[0-9a-fA-F]+|\d+)$')
ARITH = ('add', 'sub', 'imul', 'and', 'or', 'shl', 'shr', 'sar', 'sal', 'inc', 'dec', 'neg', 'not', 'sbb', 'adc')
EXT = ('movzx', 'movsx', 'movsxd', 'cdqe', 'cwde', 'cbw')
MOVS = ('mov', 'movabs', 'movaps', 'movapd', 'movups', 'movdqa', 'movdqu', 'movss', 'movsd', 'movq', 'movd')
COPY_XMM = ('movaps', 'movapd', 'movups', 'movdqa', 'movdqu')
ZERO = ('xor', 'pxor', 'xorps', 'xorpd')
NOWRITE_PREFIX = ('j', 'cmp', 'test', 'push', 'ucomis', 'comis', 'bt', 'nop', 'ret', 'jmp')


def fn(va):
    if va not in fc:
        fc[va] = Ctx(AR.Fn(mach, va))
    return fc[va]


def reg_of(name):
    if name in GPR:
        return GPR[name]
    if re.fullmatch(r'xmm\d+', name or ''):
        return (name, 128)
    return None


def split_ops(s):
    p = s.split(',', 1)
    return p[0].strip(), (p[1].strip() if len(p) > 1 else '')


def mem_kind(op):
    inner = op[op.index('[') + 1:op.index(']')]
    if 'rip' in inner:
        return 'global'
    if 'rsp' in inner or 'rbp' in inner:
        return 'stack'
    return 'ptr'


def imm_val(s):
    return int(s, 0)


class Ctx:
    def __init__(self, cf):
        self.cf = cf
        self.ins = cf.ins
        self.txt = {x.address: '%s %s' % (x.mnemonic, x.op_str) for x in cf.ins}
        self.tg = {x.operands[0].imm for x in cf.ins
                   if x.mnemonic.startswith('j') and x.operands and x.operands[0].type == capstone.CS_OP_IMM}

    def trace_reg(self, fam, s, depth=0):
        """命令 s (含む) より前で fam の値を後ろ向きに辿る。(cls, reason, value, def_addr) を返す。"""
        if depth > 12:
            return ('未決', 'depth', None, None)
        k = s
        while k >= 0:
            if k + 1 < len(self.ins) and self.ins[k + 1].address in self.tg:
                return ('未決', 'merge_at_call' if k == s else 'merge', None, None)
            x = self.ins[k]
            if x.mnemonic == 'call':
                if fam in ('rax', 'xmm0'):
                    return ('未決', 'call_ret', None, hex(x.address))
                if fam in VOLATILE:
                    return ('復元不能', 'call_clobber', None, hex(x.address))
                k -= 1
                continue
            if x.mnemonic in ('ret', 'jmp'):
                return ('未決', 'branch', None, hex(x.address))
            if x.mnemonic.startswith(NOWRITE_PREFIX):
                k -= 1
                continue
            dst, src = split_ops(x.op_str)
            if fam in self.cf.rw(x)[1] or (reg_of(dst) and reg_of(dst)[0] == fam):
                return self.def_reg(fam, x, dst, src, k, depth)
            k -= 1
        return ('未決', 'entry', None, None)

    def def_reg(self, fam, x, dst, src, k, depth):
        mn, at = x.mnemonic, hex(x.address)
        info = reg_of(dst)
        w = info[1] if info else 0
        mask = (1 << w) - 1 if w else M64
        if mn in ('movzx', 'movsx', 'movsxd') and reg_of(src) and not fam.startswith('xmm'):
            sfam, sw = reg_of(src)
            cls, why, val, da = self.trace_reg(sfam, k - 1, depth + 1)
            if cls == '実値化':
                v = val & ((1 << sw) - 1)
                if mn != 'movzx' and (v >> (sw - 1)) & 1:
                    v -= 1 << sw
                return ('実値化', 'ext_' + mn, v & mask, at)
            return (cls, 'ext_' + why if cls == '復元不能' else 'chain>' + why.split('>')[-1], None, da)
        if mn in ('add', 'sub', 'and', 'or') and IMM.match(src) and w >= 32 and not fam.startswith('xmm'):
            cls, why, val, da = self.trace_reg(fam, k - 1, depth + 1)
            if cls == '実値化':
                c = imm_val(src)
                v = {'add': val + c, 'sub': val - c, 'and': val & c, 'or': val | c}[mn]
                return ('実値化', 'arith_imm', v & mask, at)
            return (cls, 'arith_' + why if cls == '復元不能' else 'chain>' + why.split('>')[-1], None, da)
        if mn in ARITH:
            return ('未決', 'arith' + ('_load' if '[' in src else ''), None, at)
        if mn == 'lea':
            return ('未決', 'lea_' + mem_kind(src), None, at)
        if '[' in src:
            return ('未決', 'load_' + mem_kind(src), None, at)
        if mn in ZERO and dst == src and w:
            if w >= 32:
                return ('実値化', 'zero_idiom', 0, at)
            return ('未決', 'partial_zero', None, at)
        if mn in MOVS and IMM.match(src) and not fam.startswith('xmm'):
            if w >= 32:
                return ('実値化', 'mov_imm', imm_val(src) & mask, at)
            return ('未決', 'partial_imm', None, at)
        if mn in MOVS and reg_of(src):
            sfam, sw = reg_of(src)
            if not fam.startswith('xmm') and w >= 32 and sw >= w and mn == 'mov':
                cls, why, val, da = self.trace_reg(sfam, k - 1, depth + 1)
                return (cls, why, (val & mask) if val is not None else None, da)
            if fam.startswith('xmm') and mn in COPY_XMM:
                cls, why, val, da = self.trace_reg(sfam, k - 1, depth + 1)
                return (cls, why, val, da)
            return ('未決', 'partial_copy', None, at)
        if mn in EXT:
            return ('未決', 'ext', None, at)
        return ('未決', 'other:' + mn, None, at)

    def trace_slot(self, disp, s, depth=0):
        """[rsp+disp] (スタック引数の 8 byte スロット) の値を後ろ向きに辿る。"""
        if depth > 12:
            return ('未決', 'depth', None, None)
        k = s
        while k >= 0:
            if k + 1 < len(self.ins) and self.ins[k + 1].address in self.tg:
                return ('未決', 'merge', None, None)
            x = self.ins[k]
            if x.mnemonic == 'call':
                return ('復元不能', 'call_clobber', None, hex(x.address))
            if x.mnemonic in ('ret', 'jmp'):
                return ('未決', 'branch', None, hex(x.address))
            if not x.mnemonic.startswith('j') and any(
                    m['write'] and m['base'] == 'rsp' and m['disp'] == disp for m in ldmach.memops_of(self.cf.cs, x)):
                dst, src = split_ops(x.op_str)
                at = hex(x.address)
                parts = dst.split()
                size = SIZE.get(parts[0]) if parts else None
                if size == 64 and IMM.match(src):
                    return ('実値化', 'mov_imm', imm_val(src) & M64, at)
                if size == 64 and reg_of(src) and reg_of(src)[1] == 64:
                    cls, why, val, da = self.trace_reg(reg_of(src)[0], k - 1, depth + 1)
                    return (cls, why, val, da)
                if size == 64 and src.startswith('xmm'):
                    cls, why, val, da = self.trace_reg(src, k - 1, depth + 1)
                    return (cls, why, val, da)
                return ('未決', 'stack_narrow', None, at)
            k -= 1
        return ('未決', 'entry', None, None)


rows = []
cnt = collections.Counter()
xtab = collections.Counter()
for r in d['site_detail']:
    if r['status'] != 'matched':
        continue
    cva = int(r['caller'].split('_')[1], 16)
    tva = int(r['callee'].split('_')[1], 16)
    ctx = fn(cva)
    ins = ctx.ins
    calls = [i for i, x in enumerate(ins) if x.mnemonic == 'call' and x.operands
             and x.operands[0].type == capstone.CS_OP_IMM and x.operands[0].imm == tva]
    if r['k'] >= len(calls):
        continue
    ci = calls[r['k']]
    for pos_s, src in (r.get('src') or {}).items():
        if src == 'imm':
            continue
        pos = int(pos_s)
        kind = r['args'][pos_s]
        if pos < 4:
            cls, why, val, at = ctx.trace_reg(AR.REGS[pos], ci - 1)
        else:
            cls, why, val, at = ctx.trace_slot(0x20 + 8 * (pos - 4), ci - 1)
        cnt[cls] += 1
        xtab[(src, why, cls)] += 1
        rows.append({'caller': r['caller'], 'callee': r['callee'], 'k': r['k'], 'pos': pos, 'kind': kind,
                     'ledger': src, 'class': cls, 'reason': why,
                     'value': (hex(val) if val is not None else None), 'def': at,
                     'def_insn': (ctx.txt.get(int(at, 16)) if at else None)})
print('[nonimm-class] 非 imm 台帳 %d 件' % len(rows))
for k in ('実値化', '復元不能', '未決'):
    print('  %-8s %d' % (k, cnt[k]))
print('[nonimm-class] 台帳 kind × 理由 × 区分')
for (src, why, cls), v in sorted(xtab.items()):
    print('  %-14s %-22s %-8s %d' % (src, why, cls, v))
json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(a.fixes)), 'nonimm_class_rows.json'), 'w'), indent=1)
