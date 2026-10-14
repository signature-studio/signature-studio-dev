#!/usr/bin/env python3
"""set_other 台帳の imm 非定数 55 件 (#1660 / M11-N112) の値を、旧値の def 接続で決める.

m11_setother_imm_class.py が partial_write / stack_partial / arith と分類した引数について、
直前の書込命令 w の「旧値」を、w より前の直線区間を後ろ向きに辿った最後の def から求める。
  - 同じレジスタ族 (r8/r8d/r8w/r8b 等) または同じ [rsp+disp] スロットの最後の書込を探す。
  - 途中に分岐先 (jump target)・call (volatile 族) があれば、旧値は一意に決まらないので未決とする。
  - 旧値が定数 (xor r,r / mov r,imm / add|sub r,imm の連鎖) に辿れた時だけ値を決める。
値の決め方 (x86-64):
  32bit レジスタ書込は上位 32bit をゼロ拡張。8/16bit 書込は上位ビットが旧値のまま。
  スタックの dword 書込は qword スロットの下位 32bit だけを置換する。
使い方: python3 m11_setother_ssa_value.py FIXES.json --pe PE
出力: 決まった件数 / 未決件数 (理由別) を stdout、全行を ssa_value_rows.json に FIXES.json と同じ dir へ書く。
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
W32 = 0xffffffff
ARG_FAM = {'rcx': 'rcx', 'ecx': 'rcx', 'cx': 'rcx', 'cl': 'rcx', 'rdx': 'rdx', 'edx': 'rdx', 'dx': 'rdx', 'dl': 'rdx',
           'r8': 'r8', 'r8d': 'r8', 'r8w': 'r8', 'r8b': 'r8', 'r9': 'r9', 'r9d': 'r9', 'r9w': 'r9', 'r9b': 'r9',
           'rax': 'rax', 'eax': 'rax', 'ax': 'rax', 'al': 'rax'}
WIDTH = {'rcx': 64, 'ecx': 32, 'cx': 16, 'cl': 8, 'rdx': 64, 'edx': 32, 'dx': 16, 'dl': 8,
         'r8': 64, 'r8d': 32, 'r8w': 16, 'r8b': 8, 'r9': 64, 'r9d': 32, 'r9w': 16, 'r9b': 8,
         'rax': 64, 'eax': 32, 'ax': 16, 'al': 8}
VOLATILE = {'rcx', 'rdx', 'r8', 'r9', 'rax'}
MEMRE = re.compile(r'^(byte|word|dword|qword) ptr \[rsp \+ 0x([0-9a-f]+)\]$')
SIZE = {'byte': 8, 'word': 16, 'dword': 32, 'qword': 64}


def F(va):
    if va not in fc:
        fc[va] = AR.Fn(mach, va)
    return fc[va]


def targets(cf):
    t = set()
    for x in cf.ins:
        if x.mnemonic.startswith('j') and x.operands and x.operands[0].type == capstone.CS_OP_IMM:
            t.add(x.operands[0].imm)
    return t


def parse_imm(s):
    s = s.strip()
    if not re.fullmatch(r'-?(0x[0-9a-f]+|\d+)', s):
        return None
    return int(s, 0)


def sx64(v):
    return v & M64


class Ctx:
    def __init__(self, cf):
        self.cf = cf
        self.ins = cf.ins
        self.tg = targets(cf)
        self.idx_of = {x.address: i for i, x in enumerate(cf.ins)}

    def is_target(self, k):
        return self.ins[k].address in self.tg

    def reg_before(self, fam, idx, depth=0):
        """idx 直前の fam の 64bit 値。決まらなければ (None, reason)."""
        if depth > 40:
            return None, 'depth'
        j = idx - 1
        while j >= 0:
            if self.is_target(j + 1):
                return None, 'merge'
            x = self.ins[j]
            if x.mnemonic == 'call':
                if fam in VOLATILE:
                    return None, 'call_clobber'
                j -= 1
                continue
            if x.mnemonic in ('ret', 'jmp'):
                return None, 'branch'
            dst = x.op_str.split(',')[0].strip()
            if ARG_FAM.get(dst) == fam and dst in WIDTH:
                if x.mnemonic in ('div', 'idiv', 'mul', 'imul', 'cqo', 'cdq', 'xchg', 'cmpxchg', 'pop', 'cwde', 'cdqe'):
                    return None, 'opaque'
                return self.write_value(x, j, depth)
            j -= 1
        return None, 'entry'

    def write_value(self, x, j, depth):
        """命令 x (位置 j) が族への書込。書込後の 64bit 値を返す。"""
        dst, src = [p.strip() for p in x.op_str.split(',', 1)] if ',' in x.op_str else (x.op_str.strip(), '')
        fam = ARG_FAM[dst]
        w = WIDTH[dst]
        if x.mnemonic == 'mov' and src.isdigit() or x.mnemonic == 'mov' and re.fullmatch(r'0x[0-9a-f]+', src):
            imm = parse_imm(src)
            if w in (32, 64):
                return (imm & (W32 if w == 32 else M64)), 'mov_full'
            old, why = self.reg_before(fam, j, depth + 1)
            if old is None:
                return None, 'partial_old_' + why
            mask = (1 << w) - 1
            return ((old & ~mask) | (imm & mask)) & M64, 'mov_partial'
        if x.mnemonic == 'xor' and src == dst and w in (32, 64):
            return 0, 'xor_zero'
        if x.mnemonic == 'mov' and src in ARG_FAM and w in (32, 64) and WIDTH[src] >= w:
            sv, why = self.reg_before(ARG_FAM[src], j, depth + 1)
            if sv is None:
                return None, 'copy_' + why
            return sv & ((1 << w) - 1), 'copy'
        if x.mnemonic in ('add', 'sub') and w == 32:
            imm = parse_imm(src)
            if imm is None:
                return None, 'arith_nonimm'
            old, why = self.reg_before(fam, j, depth + 1)
            if old is None:
                return None, 'arith_old_' + why
            v = (old + imm) if x.mnemonic == 'add' else (old - imm)
            return v & W32, 'arith32'
        return None, 'unhandled:%s %s' % (x.mnemonic, x.op_str)

    def mem_before(self, disp, idx, depth=0):
        """idx 直前の [rsp+disp] qword の値。"""
        if depth > 40:
            return None, 'depth'
        j = idx - 1
        while j >= 0:
            if self.is_target(j + 1):
                return None, 'merge'
            x = self.ins[j]
            if x.mnemonic == 'call':
                return None, 'call_clobber'
            if x.mnemonic in ('ret', 'jmp'):
                return None, 'branch'
            m = MEMRE.match(x.op_str.split(',')[0].strip())
            if m and int(m.group(2), 16) == disp and x.mnemonic == 'mov':
                if SIZE[m.group(1)] == 64:
                    src = x.op_str.split(',', 1)[1].strip()
                    imm = parse_imm(src)
                    if imm is None:
                        return None, 'mem_nonimm'
                    return imm & M64, 'mem_qword'
                return None, 'mem_narrow'
            j -= 1
        return None, 'entry'


ctx_of = {}


def ctx(va):
    if va not in ctx_of:
        ctx_of[va] = Ctx(F(va))
    return ctx_of[va]


CLASS_OF = {(x['caller'], x['callee'], x['k'], x['pos']): x['class']
            for x in json.load(open(os.path.join(os.path.dirname(os.path.abspath(a.fixes)), 'imm_class_rows.json')))}
rows = []
cnt = collections.Counter()
for r in d['site_detail']:
    if r['status'] != 'matched':
        continue
    cva = int(r['caller'].split('_')[1], 16)
    tva = int(r['callee'].split('_')[1], 16)
    C = ctx(cva)
    cf = C.cf
    calls = [i for i, x in enumerate(cf.ins) if x.mnemonic == 'call' and x.operands and x.operands[0].type == capstone.CS_OP_IMM and x.operands[0].imm == tva]
    if r['k'] >= len(calls):
        continue
    ci = calls[r['k']]
    for pos_s, src in (r.get('src') or {}).items():
        if src != 'imm':
            continue
        pos = int(pos_s)
        if CLASS_OF.get((r['caller'], r['callee'], r['k'], pos)) in (None, 'full_const'):
            continue
        reg = AR.REGS[pos] if pos < 4 else None
        wi = None
        j = ci - 1
        while j >= 0:
            x = cf.ins[j]
            if x.mnemonic in ('call', 'ret', 'jmp') or x.mnemonic.startswith('j'):
                break
            if reg:
                hit = reg in cf.rw(x)[1]
            else:
                hit = any(m['write'] and m['base'] == 'rsp' and m['disp'] == 0x20 + 8 * (pos - 4) for m in ldmach.memops_of(cf.cs, x))
            if hit:
                wi = j
                break
            j -= 1
        row = {'caller': r['caller'], 'callee': r['callee'], 'k': r['k'], 'pos': pos, 'insn': None,
               'value': None, 'why': None}
        if wi is None:
            row['why'] = 'no_write'
            rows.append(row); cnt['undecided:no_write'] += 1
            continue
        wx = cf.ins[wi]
        row['insn'] = '%s %s' % (wx.mnemonic, wx.op_str)
        if reg:
            dst = wx.op_str.split(',')[0].strip()
            if ARG_FAM.get(dst) is None:
                # 書込先が引数族ではない (例: 間接 mov)。未決
                row['why'] = 'not_reg_write'
                rows.append(row); cnt['undecided:not_reg_write'] += 1
                continue
            v, why = C.write_value(wx, wi, 0)
        else:
            m = MEMRE.match(wx.op_str.split(',')[0].strip())
            if not m:
                row['why'] = 'mem_fmt'
                rows.append(row); cnt['undecided:mem_fmt'] += 1
                continue
            disp = int(m.group(2), 16)
            size = SIZE[m.group(1)]
            imm = parse_imm(wx.op_str.split(',', 1)[1].strip())
            if size == 64:
                v, why = (imm & M64, 'mem_full') if imm is not None else (None, 'mem_nonimm')
            elif size == 32 and imm is not None:
                old, ow = C.mem_before(disp, wi)
                if old is None:
                    v, why = None, 'mem_old_' + ow
                else:
                    v, why = ((old & ~W32) | (imm & W32)) & M64, 'mem_dword_partial'
            else:
                v, why = None, 'mem_size%d' % size
        row['value'] = None if v is None else '0x%x' % v
        row['why'] = why
        rows.append(row)
        cnt[('decided:' + why) if v is not None else ('undecided:' + why)] += 1
        if row['value'] is None:
            cnt['undecided'] += 1
        else:
            cnt['decided'] += 1

print('[ssa-value] imm 非定数 (partial/stack/arith) 対象 %d 件' % sum(1 for x in rows if x['insn'] is not None))
for k in sorted(cnt):
    print('  %-44s %d' % (k, cnt[k]))
json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(a.fixes)), 'ssa_value_rows.json'), 'w'), indent=1)
